# 念响AI · 内容OS

面向个人 IP 与一人公司的开源内容 Skill。阿响和你一起聊素材、挖选题、写朋友圈、做口播；需要保存时，再按你的授权连接个人内容知识库。

**当前公开内测：v0.1.0-beta.21 · MIT 开源。**

这一版让新任务先核验相关飞书知识版本，同轮改稿沿用，网络不可用时才使用可信缓存；同时改善历史建议追溯、标题语义、正文精简和图文关系验收。

## 内测用户从这里开始

**[下载当前 Skill 安装包 →](https://github.com/KaenZhong/nianxiang-content-os/releases/download/v0.1.0-beta.21/nianxiang-content-os-0.1.0-beta.21.zip)** · **[查看更新说明 →](https://github.com/KaenZhong/nianxiang-content-os/releases/tag/v0.1.0-beta.21)**

[全部公开内测版本](https://github.com/KaenZhong/nianxiang-content-os/releases) · [复制通用安装提示词](BETA-START.md#可复制提示词)

把提示词发给你准备使用的 Agent，它会检查当前平台、协助取得完整 Skill、引导确认私人目录，再开始第一份素材共创。没有私人知识库也能先试用。

若需要手动下载：

1. 在 [beta.21 Release](https://github.com/KaenZhong/nianxiang-content-os/releases/tag/v0.1.0-beta.21) 下载标准安装ZIP、`SHA256SUMS` 和 `LICENSE`，核对ZIP摘要。
2. 首次安装时解压并导入完整的 **`nianxiang-content-os/` 目录**；已有安装将标准ZIP交给受控更新入口，不直接覆盖目录。
3. 在目标 Agent 中发送[安装提示词](BETA-START.md#可复制提示词)，分别确认实际安装、当前对话读取、新会话生效和私人目录状态。

源码下载仍可用 Code → Download ZIP，但包含仓库外壳，不能直接用作受控更新包。

根目录的 `tools/` 是维护者工具，用户无需安装。MIT许可保存在根目录 [LICENSE](LICENSE)；下载与分发副本时保留许可及版权声明。已有念响安装先检查版本，按[受控更新](nianxiang-content-os/references/maintenance/releases.md)处理。

## 更新与生效

已有明确的官方来源更新指令沿用，不重复确认内部步骤；发生来源、目标或冲突处置范围变化时再确认。源码ZIP须按原发行清单整理为标准包，技能路径经过符号链接时先核对真实入口。具体流程见[受控更新](nianxiang-content-os/references/maintenance/releases.md)。

磁盘更新成功、当前对话重新读取新版、新会话实际装载新版分别核验。云端平台可能按会话从受管源重装技能，未核验受管源及新会话前不承诺持续生效。

## 你可以怎么用

| 需求 | 可以直接说 |
|---|---|
| 聊素材 | 阿响，先聊聊这段经历值得讲什么。 |
| 挖选题 | 阿响，从下面素材挖几个选题，我选好再写。 |
| 写朋友圈 | 阿响，用下面素材写朋友圈，面向……。 |
| 做口播 | 阿响，把下面这篇稿改成自然口播。 |

保存作品、建立知识库和安装是分别确认的动作；安装不会自动创建你的飞书知识库。完整方法由 [SKILL.md](nianxiang-content-os/SKILL.md)统一导航。

## 内测范围

- beta.21是当前公开使用基线；历史beta.10兼容试验不作为推荐安装版本。
- 本地隔离环境的178项自动测试通过。跨平台完整旅程、真实账号能力和云端重启持久性仍须按实际环境验收。
- 没有飞书工具仍可基于当轮素材共创；长期保存和恢复取决于实际文件及账号能力。
- 标准Release安装包与SHA-256校验文件已提供；仍没有自动下载更新功能（release_source=null）。冻结公共包内的候选交付描述以本仓库的公开许可及发行说明为准。

## 反馈与维护

反馈请到 [Issues](https://github.com/KaenZhong/nianxiang-content-os/issues)，提供平台、版本、复现步骤、预期与实际结果，并对截图和内容脱敏。贡献及版本维护见 [维护规则](AGENTS.md)；公共代码和文档采用 [MIT](LICENSE)，用户私人知识与创作内容不属于公开包。

维护者检查：

```sh
python3 -B nianxiang-content-os/scripts/check_public_release.py
python3 -B nianxiang-content-os/scripts/manage.py doctor --offline
python3 -B -m unittest discover -s nianxiang-content-os/tests -q
```

开发者：卡昂（KaenZhong） · 公众号：卡昂AI超能玩 · 反馈：kaenzhong@foxmail.com
