# 念响AI · 连接配置与迁移

本文件负责账号、私人目录、实时目标与保存核验。飞书正文是个人知识的权威；配置只负责寻址。首次搭建先读[建库引导](bootstrap.md)。纯素材创作没有连接前置。

## 私人目录

公开Skill与个人资料分开。默认私人根为当前系统用户的 `.nianxiang`，可由 `NIANXIANG_HOME` 或命令的 `--data-dir` 指定；优先级为显式参数、环境变量、默认值。根目录不得在Skill内部，也不得包含Skill。多账号每次明确选择 `--profile <UUID>`；不根据昵称、工作目录或上次平台猜配置档。

`<profile>`表示选定的 `<data-root>/profiles/<UUID>`，是本地私有目录的记号，不是包内相对路径：

- `local-config.json`：schema=5，13知识映射与四张Base表；不保存认证密钥。
- `state.json`：布局版本1，账号、空间与连接启用状态。
- 旧 `user-profile.json`：迁移前的已授权称呼，仅保留供显式迁移，不再新增。
- 旧 `rules.local.json`、`business-conventions.md`：保留范围与来源，按[个人源协议](personal.md)显式归位；长期权威是飞书，不直接继续追加旧文件。
- `snapshots/context.json`：原子发布的上下文包；单页`<knowledge_id>.json`为旧版兼容镜像；含账号、空间、对象、修订、读取时间和当前/过期状态。飞书内容不因被缓存就自动成为已确认事实。
- `tasks/<task_id>.json`：版本化任务检查点，只存来源和产物引用、必要选择及下一步，不代替正文。
- `derived/`：可重建的个人源投影和显式导出的摘要，不能回写源。
- `context-sync.json`：同步历史状态及已知源失效，不含凭据。
- `pending/<operation_id>.json`：获具体授权后的保存请求与结果；包括saved操作的幂等记录。未授权素材不进入队列。

包内 `local/`只带两份占位示例，不能直接作为真实连接使用。旧安装 `local/`不会被新版隐式读取。其他Skill的私人文件属于其各自规范，不随此目录调整。

## 创建配置档和连接已有库

先完成[安装阶段的私人目录初始化](../system/installation.md)：只读扫描，展示完整路径，首次创建/接管获真实确认后创建或复用并回读。此步骤不依赖飞书登录。profile create只接受已初始化的私人根，不再隐式创建根目录。

由阿响检查当前会话是否有执行Python、读写本地文件和调用用户身份飞书工具的能力，再让用户选择知识库位置。无需用户抄写token。

Python路径从Skill根运行：

```bash
python3 scripts/manage.py doctor --offline
python3 scripts/manage.py --data-dir '<私人根>' profile create --entry-url '<已确认Wiki入口>' --consent '<用户实际授权>'
python3 scripts/init_local_config.py --data-dir '<私人根>' --profile '<返回UUID>' --entry-url '<Wiki入口>'
```

配置档创建会实时核验用户身份并绑定空间。初始化命令先发现现有骨架并预览，不创建远端页面。用户允许保存配置后加 `--write`；已有配置的替换还需明确同意及 `--overwrite`。写入后运行：

```bash
python3 scripts/validate_local_config.py --data-dir '<私人根>' --profile '<UUID>'
python3 scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' profile verify
```

`profile verify`核验当前账号、全部映射和四表身份后启用连接。标题缺失、重复、类型或父子关系不符时停止；缺骨架走建库流程。显式文件参数只用于隔离验证，不能绕过账号绑定或把私人文件写回公共包。

## 实时核验与读取

选择档案后，仅从该档读取配置。接受 `knowledge_backend=feishu`、`identity=user`、`fail_closed=true`、schema=5及完整13映射、四表。未知对象、占位符、同名、跨空间、父节点变化或token配对变化都停止对应访问，不猜相似节点。

正文用obj_token；节点身份与父子关系用node_token。资产分类文档在`content.assets`的直属、同空间、唯一精确标题的docx节点中按契约动态发现，不扩大到其他子树；`02｜内容范式库`同样只在`methodology.current`直属子节点中动态发现，核对唯一精确标题、同空间、同父节点、docx类型和token配对。`content.methods`固定映射到其直属《01｜创作方法与规则》，实质方法及私人规则读写不写导航页。动态子节点操作由原生工具按同一核验与授权流程完成。

普通新任务按[飞书核验与本地缓存](../system/synchronization.md)从选定profile核验相关源版本，未变复用正文；同任务固定已读版本。示例：

```bash
python3 scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge read content.strategy expression.baseline --show-private-content
```

默认read先核验相关源修订，变化才读正文，整组成功原子发布；`--cache-only`只用于明确的本地读取和同轮恢复，`--refresh`必须成功核验，不能离线降级；具体素材、历史作品与Base对象仍按需实时读取。换平台须明确选择该环境配置档，不假定旧电脑的profile或后台能力可用。

网络失败保留匹配的本地副本，明确它的核验日期及本轮未实时核验；远端不可用时普通读取可回退到未失效的可信副本。账号不符、节点结构变化、已知权限或个人源损坏使受影响缓存失效，停止对应个性化，不能当普通离线降级。需要最新事实或具体保存仍须实时核验；无可信快照也可用当前素材继续独立创作。

## 授权保存与恢复

请求必须绑定稳定operation_id、具体对象/业务键、允许动作、基础revision、精确内容及用户原始授权。更改账号、空间、对象、动作或正文使原授权失效。获授权后：查真实账号与最新目标 → 按作品键/选题键查重 → 检查基础revision → 在私人目录登记 → 写入 → 回读真实对象和相关字段。已有对象只更新指定字段，不从旧快照全量覆盖。

```bash
python3 scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge save --request '<私人请求JSON>' --consent '<用户实际保存指令>'
python3 scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge pending
python3 scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge reconcile --operation-id '<原operation_id>'
```

`--consent`记录已有授权，不能由Agent替用户编造。请求格式见[请求示例](../../assets/templates/save-request.example.json)。脚本支持配置内Base记录的create/update，及Docx的非空纯文本append、单行精准replace。复杂文档结构、动态子文档创建及附件需原生工具按实际契约处理；不支持的脚本动作blocked，不改成全文覆盖。

只有saved可以说“已保存”。pending表示还未尝试远端写入；uncertain表示已尝试但无法核实；conflict表示基础版本或业务键冲突；blocked表示身份、授权、权限或能力不满足。保存派发前标记受影响旧缓存失效；回读成功后更新源快照，缓存更新失败须保留失效标记。原生工具写入也按[缓存协议](../system/synchronization.md#保存与失效闭环)执行invalidate与sync，不把远端保存成功当作本地已同步。

恢复先查询真实对象。同一operation_id绑定原请求，不重复创建；源变化或新范围重新决定。已尝试而未找到结果时保持uncertain，人工核查后才允许新操作，不盲目重放。Base写前检查与写后回读没有分布式条件更新保证，首版同一资料一次由一个Agent修改。

## 配置结构升级

旧schema=4配置不直接启用新版连接。使用`profile upgrade-plan --output`只读预览，`profile upgrade-apply --plan --consent`在具体授权内升级。升schema前实时核验所有旧映射；旧导航存在非空、重复或损坏的私人规则机器段时blocked，须先按[个人源协议](personal.md)授权迁移正文、回读并移除旧段，不能自动忽略或丢失规则。沿已授权的结构调整范围保留原有12映射与四表，核验`methodology.current`直属《01｜创作方法与规则》并新增`content.methods`，升级schema=5；服务案例与范式子库仍动态发现，不增加固定映射。写入配置后重新验证账号、13映射与四表，再刷新快照和私人规则投影。无法定位、同名、跨空间或token配对变化时停止，不能猜目标或用旧导航正文兜底；私人规则机器段的唯一源迁移见[个人源协议](personal.md)。

## 旧资料迁移与发行

仅在用户授权的来源与目标间复制旧local资料：先预览文件与摘要，再执行copy，再复核。目标已有不同内容、源在预览后变化或路径重定向时停止；原件保留，不切换旧安装。旧Markdown速照标为待源核验，不能直接充作新版最新JSON快照。

```bash
python3 scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' migration plan --legacy-dir '<旧local目录>' --output '<私人迁移计划JSON>'
python3 scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' migration apply --plan '<私人迁移计划JSON>' --consent '<用户实际复制授权>'
```

公开包可运行`python3 -B scripts/check_public_release.py`核验目录排除；维护者额外用`--private-source <包外维护源>`只读比对部署值，或者在既有维护源运行原检查脚本。两类检查分开报告，不在公开包补真实配置。发行排除私人目录、旧local实际文件、tasks、derived、pending、snapshots和缓存。

版本0.1.0-beta.1已实现个人源、派生投影、持久任务、受控更新和显式旧名公共核心迁移；读取/迁移见[个人源协议](personal.md)，任务恢复见[任务流程](../system/workflow.md)。本文原有本地私人文件说明属于迁移前兼容布局，不是新增长期资料的权威；新归属见[数据归属](../system/data-ownership.md)。当前交付目录已按清单核验；需要压缩分发时再生成并核验ZIP。未确定远端仓库与许可证，不宣称正式开源发布。

## 无脚本平台

具备飞书原生工具的平台可依据相同结构、账号、目标、授权和回读契约建库与使用。没有文件系统则不承诺本地快照、持久待同步队列或脚本更新；断线状态留在当前会话，下一会话重新读取飞书。飞书登录由当前会话实际提供的认证工具承担，不复制CLI认证密钥、不降为bot身份。
