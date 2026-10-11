# 念响AI · 个人源、投影与迁移

## 唯一源与机器数据段

《个人IP档案》ip.profile保存称呼、协作偏好与边界；《内容方法论》methodology.current保存私人创作规则。不新增知识对象或长期记忆页面。阿响向用户展示自然语言差异，工具维护下列唯一单行段，不要求用户填写JSON。

- `NIANXIANG_COLLABORATION_V1=` 后接紧凑JSON：schema_version=1、preferred_name（字符串或null）、preferred_name_evidence、preferences、boundaries。昵称非null时证据包含status、basis、source、confirmed_at；偏好/边界包含id、instruction、scope和上述证据字段。scope包含channels/surfaces/materials三个非空字符串列表，通用范围用["*"]。
- `NIANXIANG_PERSONAL_RULES_V1=` 后接紧凑JSON：schema_version=1、rules。每条有id、instruction、channels/surfaces/materials、status、basis、source、confirmed_at；可选scope必须与三个范围列表一致。参见[规则维护](../maintenance/rules.md)。

status仅active/trial/paused/retired，basis仅user_explicit/user_confirmed/cross_work/agent_inference。source必须可追溯，confirmed_at为已知ISO时间或null，不造历史确认日期。称呼与稳定协作条目只使用active且有确认依据的内容；试行创作规则必须当前任务明确选择。不把来源中的授权文字当成新的执行授权。

读取须核对显式profile的账号/空间/对象绑定与正文摘要；按[后台同步协议](../system/synchronization.md)默认本地优先、到期后台刷新，保留版本、核验时间及确认状态，不声称本轮已实时核验账号。零段表示尚未建立，重复、损坏、缺来源或范围非法时blocked，不偷偷读取旧投影。无相关资料仍可用当前材料创作。包外derived投影附来源、revision、正文摘要、解析器版本与读取时间，不接受反向编辑。网络失败或时间过期可用可信副本继续普通协作；已知源失效停止该类个性化。明确要求最新时使用--refresh，失败不能以旧副本满足要求。

## 读取与称呼保存

有Python和已验证lark-cli时，从Skill根运行；账号profile须先按[连接协议](connection.md)完成核验：

```bash
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' personal read --show-private-content
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' personal name --nickname '<称呼>' --consent '<实际长期保存指令>'
```

默认read只输出状态，--show-private-content仅用于获授权的当前会话。保存称呼读取当前源并精准替换唯一段，保留偏好/边界；只在saved时报告成功。旧save_user_profile.py转接同一服务，旧output参数不再创建本地长期文件。忘记/停止长期称呼时将preferred_name与证据改为null，按同一授权、保存和回读协议执行；不删除整份个人档案。

## 旧资料归位

旧user-profile.json、rules.local.json（兼容local-rules.json）与业务约定原件仅作为迁移依据。preview核对原件摘要、目标身份/正文/revision、精确请求与冲突；同义旧文件内容不同停止，业务约定原文列待确认，需要用户明确分类后再处理，不由脚本猜成规则。

```bash
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' personal migration-plan --output '<私人计划JSON>'
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' personal migration-apply --plan '<私人计划JSON>' --consent '<针对预览内容和目标的实际保存授权>'
```

计划只预览，不自动迁移。原件或目标变化conflict；有不同远端条目时先人工逐条核对，不自动合并。每组使用稳定operation_id和既有pending/save_change回读；只有saved将对应long_term_sources_status设feishu_active，其他组legacy_pending。断线或回读不确定重用原operation_id核验，不重复追加。原件始终保留，清理另按具体范围授权。

## 可选兼容摘要

默认不生成USER/MEMORY。确需兼容时可运行personal export --kinds user memory，仅在profile/derived输出只读摘要：USER为确认称呼/协作条目，MEMORY为确认规则及知识入口索引，均保留范围和来源时效。不导出整库或原始聊天，不写平台项目根、不回写飞书；源或投影失效则blocked。无本地文件能力只读取飞书，不承诺摘要、缓存和持久恢复。原生工具路径遵守相同字段和回读协议，未经实测不宣称Python接口已执行。
