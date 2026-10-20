# 念响AI · 飞书核验与本地缓存

飞书是私人长期知识的唯一权威，本地是可重建的工作副本。本协议负责读取、缓存失效与刷新；连接和具体保存仍按[连接协议](../knowledge/connection.md)。

## 使用流程

1. 新一轮实质共创从显式选定profile按需核验相关飞书源：核对用户及节点，已有可信缓存时先查Docx修订号，版本不变复用正文，变化才获取全文；没有元数据能力则读取全文比较。普通新任务不再等24小时才检查，也不默认先用旧版、后台补查。轻聊、状态查询和纯维护不为此加载整组私人知识。
2. 同一轮持续讨论和改稿沿用已读版本与本轮最新要求，不逐条消息重复联网。Agent保留本次generation和源revision；用户明确告知新规则、停用要求或关键边界变化时立即处理受影响源，不静默更换已确认稿件。
3. 所需源整组核验成功后，原子发布上下文包并固定本轮读取结果。无变化只更新核验时间，不改变正文同步时间。读取七页的能力不代表每篇要加载七页全文。
4. 网络暂不可用时，普通读取可回退到绑定、对象和摘要均有效且未被标记失效的缓存，返回offline_fallback、current=false、account_verified_live=false；说明实际核验日期和未校准范围。没有可信副本时使用本轮材料继续独立创作，不假称个性化校准。账号不符、权限拒绝、目标变化、源损坏和已知新修订不属于普通离线，受影响旧内容停止使用。
5. 明确要求最新的--refresh必须成功访问远端，失败不能以缓存满足。--cache-only仅用于明确只读本地或同轮任务恢复，不作为新共创的默认入口，不启动后台进程。不要用该选项绕过应有的版本核验。

## 保存与失效闭环

获具体授权的保存仍实时核验最新目标、查重、检查基础版本并回读。脚本在派发长期源写入前标记旧缓存失效，成功后直接使用已核验回读结果更新快照，不再次下载同一正文。写入结果不明或缓存发布失败时，保留失效标记与分别可核验的保存状态；远端saved不等于本地同步成功。

通过飞书CLI或其他原生工具直接修改已缓存的长期源时，在派发写入前运行knowledge invalidate对应知识ID；写后核验远端，再knowledge sync对应源。无法调用本地管理入口时在当前任务明确记录该源失效，后续不得依赖旧缓存，不宣称持久失效登记已完成。不能手工改派生投影冒充源同步。动态范式子文档不在固定缓存范围时，不为它创建额外长期快照；仅在导航源也发生修改时刷新导航源。

读取过程中发现修订变化即标记旧副本失效；后续下载或同组其他页失败，不能回退到已知旧版。只有成功核验并发布的页解除自身失效，单页成功不证明其他页恢复。并发的新保存、配置变化或新失效记录使旧同步结果放弃发布，不能覆盖新缓存。

## 范围与状态

长期上下文范围：content.strategy、audience.needs、ip.profile、expression.baseline、methodology.current、content.methods、content.assets。私人方法与规则从content.methods解析，methodology.current只作导航。素材、聊天记录、指定母稿、Base选题/作品与发布状态按实际对象实时读取；服务案例、内容范式子库按任务发现，不遍历整库。

<profile>/snapshots/context.json是带generation和绑定摘要的原子上下文包；单页JSON为兼容镜像。derived投影可重建，不是独立权威。context-sync.json保存上次操作结果与失效标记，不含凭据。

checked_at是上次成功远端核验时间，body_synced_at是正文同步时间，read_at兼容原正文读取时间。本地读取不延长成功时间。stale只表示超过24小时的年龄提示，不再决定是否核验远端；未过24小时也不保证源未变。

sync-status不联网，current=false；synced只表示记录的那次同步成功，必须结合finished_at、knowledge_ids和invalidations判断，不能宣称本次已核验最新。读取结果的current=true才表示本次前台核验成功。后台started只表示进程已启动，不证明完成或当前上下文已更新。

## 管理入口与兼容

从Skill根调用，显式选择profile：

```bash
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge read content.strategy expression.baseline --show-private-content
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge read content.strategy --cache-only --show-private-content
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge read content.strategy --refresh --show-private-content
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge invalidate content.methods
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge sync content.methods
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' knowledge sync-status
```

read默认核验所需源，sync显式等待所选源刷新，省略ID时刷新七页。personal read同样默认核验；旧--allow-stale只保留兼容，不使--refresh降级。task resume沿用本地检查点上下文比较版本，--refresh用于需要最新校准时；具体远端产物仍实时核验，pending不重放。

旧后台worker和单机锁保留兼容已有调用，不由默认read启动，不创建定时任务或驻留轮询。后台远端读取不占保存锁，发布短暂加锁并检查并发变化；网络失败保留可信副本与失败记录。不同设备各自缓存，不共享单机锁。没有文件能力时按需读取飞书与当前会话材料，不承诺持久缓存或失效登记；没有飞书能力时如实说明边界。
