# 念响OS · 系统任务流程

## 五类专业任务

| kind | 目标 | 按需入口 |
|---|---|---|
| strategy 策略 | 校准经营目标、受众、定位与承接 | [策略](../knowledge/strategy.md)、[知识地图](../knowledge/map.md) |
| topics 选题 | 从材料找到有来源、可比较的切口 | [选题](../creation/topics.md)、必要时[选题地图](../creation/topic-map.md) |
| creation 创作 | 创作、改稿、审稿或跨渠道复用 | [共创工作流](../creation/workflow.md)、命中渠道方法 |
| operations 运营 | 选题入池、归档、发布回填、资产与战役 | [作品](../knowledge/works.md)、[资产](../knowledge/assets.md)、[战役](../knowledge/campaigns.md) |
| review 复盘 | 依据真实反馈提出调整 | [复盘方法](review.md)、相关作品与已确认目标 |

五类共用阿响与知识服务。运营不自动发布，具体创作门禁与八项扫描只由共创工作流维护。

## mode与任务检查点

mode为discussion或execution，讨论不授权写远端，执行仍只覆盖用户指定对象与动作。先核对目标/缺口→读取必要来源与方法→共创/审阅→交付→获具体授权保存并回读→反馈与下一步。

有本地文件能力时可在包外profile/tasks维护schema=1的任务检查点。字段包含task_id、profile/account/space、version、kind/mode/status、goal、context_refs、selected_items、artifact_refs、checkpoint、next_step、operation_ids、updated_at。只存必要且已确认的选择和正文引用，不复制整段会话或稿件，不持久化原生提问请求或伪造回执ID。

status为draft/active/waiting/completed/abandoned。draft可转active/waiting/abandoned；active可转waiting/completed/abandoned；waiting可转active/abandoned；completed/abandoned只读。更新须expected_version，旧版本conflict不覆盖。改变mode须有对应的新指令。任务completed不代表作品已发布；放弃不删除历史作品。

context_refs记录knowledge_id、obj_token、revision；artifact_refs可引用配置内远端作品/文档（target/revision）、获授权的本地文件（绝对规范path、sha256、authorized_root），或missing素材标签。本地源被移走返回needs_input；不可只存标题假称能找回正文。测试环境可用临时素材，真实任务应引用稳定位置。

## 创建、更新与恢复

从Skill根使用[请求示例](../../assets/templates/task-request.example.json)，由阿响生成并填写真实来源，不让用户手填内部JSON：

```bash
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' task create --request '<私人请求JSON>' --consent '<实际任务授权>'
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' task update --task-id '<任务UUID>' --patch '<私人补丁JSON>' --expected-version 1 --consent '<实际更新指令>'
python3 -B scripts/manage.py --data-dir '<私人根>' --profile '<UUID>' task resume --task-id '<任务UUID>' --show-private-content
```

resume按[缓存协议](synchronization.md)用本地长期上下文比较检查点版本；具体远端产物实时核验账号和对象，本地产物核验摘要，pending只查现状。--refresh要求最新上下文，返回ready/needs_input/needs_revalidation/blocked。它只恢复可核验的下一步，零远端写入，不重放保存或过期选择卡。uncertain仍是不确定，不能转为已保存/已发布；新动作沿用仍有效的具体授权或补足新范围授权。

默认命令只输出状态，正文和私人选择仅显式--show-private-content。无文件能力时不承诺持久任务日志，当前会话沿用有效上下文，跨会话从飞书查回已保存对象；未保存素材如实说明缺失。需要关键决策时遵循[交互协议](interaction.md)，答案到达才推进，不把预选当确认。
