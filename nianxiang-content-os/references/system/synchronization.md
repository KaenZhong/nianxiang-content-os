# 念响AI · 使用时触发后台同步

本协议负责长期上下文的读取与刷新；账号连接、具体保存及远端对象恢复仍按[连接协议](../knowledge/connection.md)。飞书是唯一长期权威，本地是可重建的工作副本。

## 使用流程

1. 首次使用没有可信副本时，明确选择已启用的profile，核验用户、节点与必要源正文，建立本地快照。失败则使用本轮素材完成独立创作，不声称已完成个性化校准。
2. 新任务按需从本地读取策略、表达及相关个人事实/规则，核对profile、账号/空间绑定、对象映射与正文摘要。普通读取不调用飞书；同任务沿用已加载的版本与已确认选择。
3. 读取时只在本地检查上次成功核验时间。默认间隔24小时，未到期直接工作；到期先固定本次读取结果，再启动一个独立后台进程，前台继续素材判断、选题或创作，不等待同步结束。`--cache-only`只读本地，不启动进程。
4. 后台实时核验用户和节点，先查Docx元数据修订号，未变不下载正文，变化才获取全文；没有元数据能力的适配器可读取全文比较。整组校验通过后原子发布一份上下文包，下次任务读取新版。同一次响应不会因后台完成而换版。
5. 获具体授权的保存仍实时核验最新目标、查重、检查基础版本并回读。脚本直接用已经核验的回读结果更新本地，不再次下载同一正文。后台旧结果若遇到新保存、配置变化或新失效标记，放弃发布，留待后续使用重试。

“24小时”是使用时的刷新判断，不是定时任务。没有使用就不运行，也不承诺闲置期间同步。后台失败退避重试同样由后续使用触发，没有驻留轮询、系统cron或AI工具定时任务。

## 同步范围与来源

背景刷新范围为六份长期上下文：`content.strategy`、`audience.needs`、`ip.profile`、`expression.baseline`、`methodology.current`、`content.assets`。后台刷新六份不等于将六份全文加入创作上下文，Agent仍只读本篇相关资料。

新给出的素材、聊天记录、指定母稿及历史作品按任务需要直接读取；Base中的选题/作品、发表状态、业务键及具体待同步操作按实际对象实时核验。后台不遍历整库历史，不写飞书、不提交沉淀、不重放pending、不自动修改策略或私人规则。

`<profile>/snapshots/context.json`是原子发布的上下文包，带generation及绑定摘要；单页JSON是兼容镜像。旧版已核验的单页快照在首次新读取时可直接复用，身份/对象/摘要损坏时停止对应个性化。包外`context-sync.json`记录后台状态、重试时间和已知失效；派生个人投影从本次选定的源版本重新解析，不作为读取权威。

时间分别记录：`checked_at`为上次成功远端核验，`body_synced_at`为正文同步时间，`read_at`兼容原正文读取时间。本地使用不延长核验期限；失败不刷新成功时间。`current=true`仅表示本次前台已实时核验；本地返回`status=local`、`current=false`、`account_verified_live=false`，不能称本轮已读取最新远端。`stale=true`表示超过刷新间隔，时间过期本身不阻塞普通共创。

## 任务连续性与失效

任务保留本次generation及各源revision引用，不静默替换正在共创的观点、事实或边界。新任务加载新版；恢复时比较本地版本与检查点，变化返回needs_revalidation。恢复具体远端产物仍要实时核验该产物，普通本地上下文恢复不因此多查整组策略。

用户本轮明确的新事实、停止使用的规则与公开边界立即生效。已知源被修改且可能影响核心判断、隐私或承诺时，停止依赖受影响的旧内容，按所需页核验；可先做不依赖它的工作。Agent在任务衔接或交付前可只读同步状态；若相关版本有重大变化，先展示差异并重新校准，不偷偷替换已确认稿件。

账号不符、已知节点变更、权限拒绝及个人机器段损坏等失效，实时读、保存和同步入口均须记录。保存锁竞争不得丢失标记。只有成功核验的页解除自身失效，单页恢复不证明其他页已恢复。已知失效期间停止相关个性化；它与网络失败、单纯超过24小时分开处理。

以下情况才需要前台等所需资料核验：没有可信副本；用户明确要求最新；已知关键事实或边界变更/冲突；建立/更换账号绑定；具体远端保存与产物恢复。`--refresh`必须成功访问远端，不能以旧缓存满足“最新”。缓存校验损坏可通过显式刷新重建。

## 运行边界

每profile一个后台worker，用独立进程与OS锁防重复。远端读取不占前台保存锁，发布时短暂加锁并检查本地版本与失效记录，整组失败不发布半套资料。网络失败保留最后可信版本，记录失败与退避；只在影响任务时说明同步延迟，普通成功不刷屏。

需要Python、持久私人目录、已认证lark-cli与宿主允许进程脱离调用继续运行。`started`仅表示成功启动，`synced`才表示完成；平台可能终止子进程，不能凭启动响应保证后续成功。没有后台能力但有文件时，只读本地并如实报告刷新未运行，必要时显式同步；没有文件时使用当前会话与按需远端读取，不宣称本地后台能力。不同设备各自缓存，不共享单机锁。

## 管理入口

从Skill根调用，显式选择profile：

```bash
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge read content.strategy expression.baseline --show-private-content
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge read content.strategy --cache-only --show-private-content
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge read content.strategy --refresh --show-private-content
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge sync
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge sync-status
```

`read`默认本地优先，过期时发起后台；`sync`是显式的前台只读刷新，省略知识ID刷新六页；状态查询不联网。personal read同样本地优先，可用`--cache-only`或`--refresh`。旧`--allow-stale`只保留参数兼容，不使`--refresh`降级。task resume默认用本地长期上下文，可用`--refresh`要求最新；远端产物始终按对象核验。
