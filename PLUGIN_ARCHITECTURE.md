# 模型无关的医院警报平台：接口设计

## 1. 目标

不是把 GIST 模型写死进 HIS，而是做一个**可插拔的预警平台**：

- GIST T1/T2 只是第一个插件；
- 以后训练好的“是否需要转诊”“是否需要进一步检查”等模型，按同一接口注册后即可接入；
- 前端、警报路由、审计、去重、权限复用，不需要为每个疾病重写一套。

## 2. 分层

```text
HIS 前端 / 医生站
   │ 读取 alert 表 / 调用 BFF
   ▼
Alert API（统一）
   ├─ 模型注册表 Model Registry
   ├─ 病例输入与字段映射 Feature Mapper
   ├─ 评分运行时 Scoring Runtime
   ├─ 警报策略引擎 Alert Policy Engine
   ├─ 警报存储/确认/去重 Alert Store
   └─ 审计与版本 Audit / Versioning
   │
   ├─ GIST T1/T2 插件
   ├─ 转诊模型插件（未来）
   └─ 其他疾病模型插件（未来）
```

## 3. 插件契约

每个模型插件提供：

```python
class RiskModelPlugin(Protocol):
    model_id: str
    version: str
    input_schema: dict          # 需要哪些字段、单位、允许缺失
    output_schema: dict         # score / flag / reasons / evidence
    def score(self, case: dict) -> "ModelResult": ...
    def alert_policy(self, result: "ModelResult", context: dict) -> "AlertSpec": ...
```

统一的 `ModelResult`：

```json
{
  "model_id": "gist_t2_v11",
  "model_version": "v11",
  "score": 0.62,
  "calibrated_score": 0.62,
  "flag": true,
  "reasons": ["hemoglobin 78", "crp 35", "age 62"],
  "evidence": {"threshold": 0.05, "calibration": "platt"},
  "disclaimer": "research prototype; not a diagnosis"
}
```

统一的 `AlertSpec`：

```json
{
  "severity": "high",
  "channel": "banner",
  "title": "GIST 风险评估提示",
  "body": "T2 高风险；建议优先评估。不是诊断。",
  "actions": ["refer_specialist", "order_imaging", "defer", "not_relevant"],
  "dedup_key": "gist:T2:encounter-123",
  "suppress_after_action": true,
  "ttl_hours": 24
}
```

## 4. 插件清单

```json
{
  "model_id": "gist_t2_v11",
  "disease": "GIST",
  "tier": "T2",
  "version": "v11",
  "owner": "ACCORD-SL",
  "inputs": [
    {"name": "age", "type": "number", "unit": "years", "required": true},
    {"name": "hemoglobin", "type": "number", "unit": "g/L", "required": true}
  ],
  "outputs": ["score", "flag", "reasons"],
  "threshold": 0.05,
  "alert_policy": {
    "default": "queue",
    "confirmed_high_risk": "banner",
    "critical": "modal"
  }
}
```

未来转诊模型只需新增一个 manifest：

```json
{
  "model_id": "referral_v1",
  "disease": "general",
  "version": "v1",
  "inputs": [{"name": "age", "type": "number"}, {"name": "crp", "type": "number"}],
  "outputs": ["score", "flag"],
  "threshold": 0.30,
  "alert_policy": {"default": "queue"}
}
```

## 5. 统一 API

```text
GET  /v1/models
GET  /v1/models/{model_id}
POST /v1/score/{model_id}
POST /v1/events/lab          # 检验事件到达，自动路由到匹配插件
GET  /v1/alerts?status=open
POST /v1/alerts/{alert_id}/ack
POST /v1/alerts/{alert_id}/dismiss
GET  /v1/audit/{encounter_id}
```

`POST /v1/score/{model_id}` 的请求体只包含标准字段：

```json
{
  "request_id": "req-001",
  "encounter_id": "enc-123",
  "patient": {"age": 62},
  "labs": {"hemoglobin": 78, "crp": 35},
  "context": {"ward": "gastroenterology"}
}
```

## 6. 警报策略引擎

模型只输出 `ModelResult`；**是否弹、用什么方式弹、弹给谁、多久后重复**由平台统一策略决定：

- `channel`：`queue` / `banner` / `modal`；
- `severity`：`info` / `medium` / `high` / `critical`；
- `dedup_key`：同一患者、同一模型、同一 episode 只保留一条；
- `suppress_after_action`：已处理/已开检查/已会诊后不再弹；
- `ttl_hours`：超时转待办或关闭；
- `rate_limit`：每个病区/医生每天最多几条中断式提醒。

这样 GIST 和未来转诊模型可以共享同一套警报治理，不会各写一套弹窗。

## 7. 输入映射

平台不假设医院字段名与模型一致。每个插件声明自己的 `input_schema`，平台负责：

- 医院 LIS 字段 → 标准字段；
- 单位换算；
- 缺失值/`<`/`>` 处理；
- 类别型尿常规编码；
- 数据时间窗（例如 T1 用入院 48h 内首次结果）。

未来模型可以有自己的输入合同，不需要改平台代码。

## 8. “直接插入就能用”的边界

接口统一后，新模型**不需要改前端/警报引擎**，但仍需要：

1. 打包成插件（manifest + predictor + preprocessor）；
2. 定义输入字段和单位映射；
3. 本地校准和阈值；
4. 警报文案/严重度/动作；
5. 本地 silent-mode 验证；
6. 签名、版本、审计。

所以是“**按契约插入**”，不是“任意代码上传即生效”。后者在医院环境不可接受。

## 9. 安全与治理

- 插件只能由管理员在部署时注册，不允许前端上传模型；
- 每个插件签名、版本固定、可回滚；
- 模型输出与警报分离，便于审计；
- 所有评分记录 `model_id`、`version`、`threshold`、`input_hash`；
- 患者数据不出院内网络；
- 每个疾病模型独立做本地验证和伦理/监管评估。

## 10. 实施顺序

1. `release_api/`：FastAPI + 插件注册 + GIST 插件；
2. 加一个**dummy 转诊插件**，证明“换模型不改平台”；
3. Docker 化，医院内网部署；
4. 先 silent mode（只写 alert 表，不弹）；
5. 再按病区开 queue/banner；
6. 最后才考虑 modal。
