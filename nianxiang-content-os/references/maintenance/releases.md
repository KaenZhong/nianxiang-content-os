# 念响AI · 公共核心更新

更新替换通用方法和管理代码。飞书知识仍在原空间，包外个人配置、快照、规则和待同步请求保持原样；更新和回退都不回滚飞书数据。开始前结束正在使用该核心的任务，同一安装一次只有一个更新操作。

当前首版支持明确指定的本地ZIP。`release_source=null`，检查更新返回`not_configured`；没有自动下载源、后台更新或GitHub正式发行。SHA-256与清单证明文件完整性，来源可信性由用户核对，不能因摘要一致就执行未知来源的代码。

## 版本编号

念响OS从`0.1.0-beta.1`独立记录公开版本。正文和发布标签可显示`v`前缀，发行清单只存版本号。0.x表示开发初期，beta.n表示同一目标版本的第n轮内测；后续稳定兼容契约形成时进入1.0.0。已经交付的版本内容固定，后续修改使用新版本号；数据结构版本独立维护。更新记录只记本产品的发行变化。

## 首次导入与旧安装

首次导入后按[安装与私人目录初始化](../system/installation.md)扫描已有根，首次确认完整路径后创建或复用并回读。公共包导入成功不等于私人目录已初始化。

首次使用从已信任、完成核验的公共目录导入，包内包含`release-manifest.json`。当前只交付文件夹；需要本地更新时再生成用于更新接口的ZIP。正式公开发布另落实仓库与许可证。

没有完整发行清单、可能含私人local文件的既有安装不能直接更新。保留原安装，在新的独立目录导入当前公共核心，按[连接说明](../knowledge/connection.md)选择个人配置档，预览并复制旧local资料；核对来源后启用知识连接。原安装、原资料都保留，具体替换仍须授权。不能在改过的安装上重做清单以绕过改动冲突。

不能执行Python但提供原生Skill导入能力的平台，通过该平台正式导入方式安装经过校验的公共包；不能声称调用了本节Python更新、持久日志或自动回退。更新前保留旧公共包，明确包外知识与资料入口，按平台真实能力验证。

## 检查和更新

由已信任的管理入口执行。以下路径均为用户指定的本地位置，占位文字不能直接执行：

```bash
python3 -B scripts/manage.py release verify --archive /path/to/trusted-package.zip
python3 -B scripts/manage.py release check-update --manifest release-manifest.json
python3 -B scripts/manage.py release status --skill-root /path/to/installed/nianxiang-content-os
```

先展示版本、来源、schema=4/layout=1、变更说明及目标安装目录，获得针对这次包与安装位置的明确更新指令。真实授权记录写入`--consent`；不能由Agent凭空生成授权。完成授权后：

```bash
python3 -B scripts/manage.py --data-dir /path/to/private-root --profile UUID \
  release apply --archive /path/to/trusted-package.zip \
  --skill-root /path/to/installed/nianxiang-content-os \
  --consent "用户实际要求更新本次指定包与安装目录的原话"
```

脚本核验单一顶层目录、所有文件与清单、schema/layout、路径、重复成员、符号链接、私人文件名和尺寸上限；ZIP里的未列文件同样拒绝。私人目录必须在核心和安装记录之外。旧核心全部文件、文件集合和清单必须匹配；本地改动得到`conflict`，不自动覆盖、不自动迁成个人规则。

通过后在核心同级的`.nianxiang-installations/<installation-id>/`加单机锁，复制并再次验包、暂存新核心、运行离线健康检查，写切换日志，备份旧核心，再通过同文件系统重命名切换。健康检查包括入口、Python/JSON结构及`doctor --offline`，只执行已获信任与具体授权的公共代码。切换后再次健康检查和摘要核验。安装记录与备份不属于公开包，也不写入个人配置档。

文件重命名、占用和权限的实际支持以当前操作系统及文件环境为准；被占用、跨文件系统或无法安全完成时停止并报告。单机锁只协调管理脚本，不能保证跨设备或另一个编辑器同时改文件的安全。本轮以进程中断验证恢复；断电持久性尚未实测。

## 回退和中断恢复

```bash
python3 -B scripts/manage.py release rollback \
  --skill-root /path/to/installed/nianxiang-content-os \
  --consent "用户实际要求回退这次更新的原话"

python3 -B scripts/manage.py release recover \
  --skill-root /path/to/installed/nianxiang-content-os \
  --consent "用户实际要求恢复本次中断更新的原话"
```

`rollback`核对当前新核心及旧备份，保留新核心副本后恢复旧核心并验证。当前核心有更新后的本地改动时得到`conflict`；回退不覆盖这些改动。回退需要明确授权，接口的第三个`consent_id`参数也必须提供。

普通失败自动尝试恢复；崩溃留下切换阶段和备份后，用`recover`查实际目录再恢复到旧核心。恢复前后核对完整文件摘要与健康状态。对已经成功的更新执行`recover`只报告`active`，不会撤销成功更新；显式撤销使用`rollback`。

如果回退或回读健康状态也失败，结果为`recovery_required`。保留安装日志、原备份、暂存和失败核心，由用户根据真实目录状态处理；不能把这个结果说成“恢复成功”。备份与中断暂存供唯一恢复用途，首版不自动清理历史安装记录。

| 结果 | 可以怎么报告 |
|---|---|
| verified | 包结构与摘要核验通过；仍须核对来源及切换授权 |
| updated / up_to_date | 新核心已切换并核验，或当前文件与指定包完全一致 |
| active | 当前已成功更新；没有需要撤销的中断 |
| rolled_back | 旧核心完整恢复并核验；个人资料保持原样 |
| conflict | 当前公共文件已改动或备份不匹配，未覆盖冲突文件 |
| blocked | 包、身份路径、能力、兼容或授权不满足 |
| recovery_required | 有未完成的切换/恢复；按日志核对，保留所有恢复对象 |
| not_configured | 未配置官方远端更新源；可明确指定本地包 |

## 维护者生成清单

在公共开发目录完成修改和排除检查后生成；对已有管理日志的安装目录命令会拒绝重做基线：

```bash
python3 -B scripts/manage.py release manifest \
  --source-dir /path/to/public-candidate --version 0.1.0-beta.4
```

清单列出除自身之外的全部公共文件、尺寸和SHA-256。任何公共文件改动后必须重新生成并核对清单；最终ZIP在发行阶段重新验收。目前清单不是签名，也不代表许可证、正式仓库或三平台实机已落实。个人优化按[规则维护](rules.md)留在私人配置档；官方核心更新不吸收私人规则。

## 名称迁移：旧名受管安装到内容OS

普通发行入口只接受nianxiang-content-os；旧名只在显式名称迁移及其恢复中接受。源与目标必须是同一父目录下不同核心目录，profile与核心、安装记录分离。目标核心或目标安装记录存在、原文件或日志已改变时停止，不覆盖。只选择同一绑定profile，不搬动或改写其文件。

```bash
python3 -B scripts/manage.py --data-dir /path/to/private-root --profile UUID \
  release migrate-plan --old-root /path/to/installed/nianxiang-content-studio \
  --new-root /path/to/installed/nianxiang-content-os --output /path/to/private-preview.json
```

预览不改变安装；省略output时仅输出状态和摘要，不能据此执行缺失的计划文件。计划含私有路径和绑定信息，应放在用户指定的安全位置，不能进入公共包，也不能写到核心、profile或安装记录内部。核对原/目标根、旧清单与日志摘要、profile绑定及步骤后，凭已有的具体迁移授权执行：

```bash
python3 -B scripts/manage.py --data-dir /path/to/private-root --profile UUID \
  release migrate-apply --plan /path/to/private-preview.json \
  --archive /path/to/trusted-os-package.zip --consent "用户实际要求此次改名迁移的原话"
```

有完整发行清单的旧名安装经暂存、旧根备份、新名切换与日志迁移核验后返回migrated；独立迁移审计保留原根、来源清单与恢复地址。若在active日志提交后中断，恢复或下一次更新/同版检查先补齐审计；审计与原日志不一致则blocked，保留双方供核对，不静默覆盖。没有有效发行清单的安装返回legacy_import_required，不生成覆盖计划，按首次导入保留原件。迁移后用新根查询status/rollback/recover；中断时使用实际仍可定位日志的旧根或新根地址。恢复核验核心与日志，成功回到旧名、旧路径及旧清单；原有普通安装日志另行保留，私人文件不改变。recovery_required不能称恢复完成。

## 公共Agent与方法的版本维护

公共定义各只有一个位置：agent/IDENTITY.md负责身份关系，agent/SOUL.md负责交流气质，agent/AGENTS.md负责作用域和执行协议，agent/methodology.md负责判断方法；系统流程与创作方法各按入口路由。首次协作在system/onboarding.md，私人协议的归属、来源与成熟度在[rules.md](rules.md)，不再维护另一套axiang目录。

日常共创不会自动演化公共人格或内置方法。纯念响问题作为可复现的版本反馈，标明现有规则覆盖、执行遗漏或真实缺口。用户明确要求修改念响时，这是单独的版本维护任务：展示具体公共差异、检查相邻边界，优先融合旧条款，在候选副本中校验结构与行为，更新入口、验收、变更记录和清单；替换安装继续遵守本篇具体切换授权。确认私人偏好不授权改公共文件；贡献公共核心须另核对可分享范围，不复制私人正文。
