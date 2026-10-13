# 念响AI · 内容OS

面向个人 IP 与一人公司的开源内容 Skill。阿响和你一起聊素材、挖选题、写朋友圈、做口播；需要保存时，再按你的授权连接个人内容知识库。

**当前内测：v0.1.0-beta.11 · MIT 开源。**

## 内测用户从这里开始

**[复制安装与首次使用提示词 →](BETA-START.md#可复制提示词)**

把提示词发给你准备使用的 Agent，它会检查当前平台、协助取得完整 Skill、引导确认私人目录，再开始第一份素材共创。没有私人知识库也能先试用。

若需要手动下载：

1. 点击本页 **Code → Download ZIP**，解压源码仓库。
2. 只导入里面完整的 **`nianxiang-content-os/` 子目录**，其中应直接有 `SKILL.md`；所有子目录一起保留。
3. 在目标 Agent 中发送[安装提示词](BETA-START.md#可复制提示词)，确认实际加载版本和私人目录状态。

根目录的 `tools/` 是维护者工具，用户无需安装。MIT许可保存在根目录 [LICENSE](LICENSE)；下载与分发副本时保留许可及版权声明。已有念响安装先检查版本，按[受控更新](nianxiang-content-os/references/maintenance/releases.md)处理。

## 你可以怎么用

| 需求 | 可以直接说 |
|---|---|
| 聊素材 | 阿响，先聊聊这段经历值得讲什么。 |
| 挖选题 | 阿响，从下面素材挖几个选题，我选好再写。 |
| 写朋友圈 | 阿响，用下面素材写朋友圈，面向……。 |
| 做口播 | 阿响，把下面这篇稿改成自然口播。 |

保存作品、建立知识库和安装是分别确认的动作；安装不会自动创建你的飞书知识库。完整方法由 [SKILL.md](nianxiang-content-os/SKILL.md)统一导航。

## 内测范围

- beta.11是当前公开使用基线；历史beta.10兼容试验不作为推荐安装版本。
- 本地隔离环境的160项自动测试通过。跨平台完整旅程、真实账号能力和云端重启持久性仍须按实际环境验收。
- 没有飞书工具仍可基于当轮素材共创；长期保存和恢复取决于实际文件及账号能力。
- 当前没有专用Release安装包，也没有自动下载更新功能。包内保留的发布前描述以本仓库的公开许可和当前说明为准。

## 反馈与维护

反馈请到 [Issues](https://github.com/KaenZhong/nianxiang-content-os/issues)，提供平台、版本、复现步骤、预期与实际结果，并对截图和内容脱敏。贡献及版本维护见 [维护规则](AGENTS.md)；公共代码和文档采用 [MIT](LICENSE)，用户私人知识与创作内容不属于公开包。

维护者检查：

```sh
python3 -B nianxiang-content-os/scripts/check_public_release.py
python3 -B nianxiang-content-os/scripts/manage.py doctor --offline
python3 -B -m unittest discover -s nianxiang-content-os/tests -q
```

开发者：卡昂（KaenZhong） · 公众号：卡昂AI超能玩 · 反馈：kaenzhong@foxmail.com
