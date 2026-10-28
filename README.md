# 念响OS · AI内容系统

**陪你聊素材、找选题、写内容，把经验慢慢积累成自己的内容资产。**

面向个人IP与一人公司的开源内容Skill。阿响是念响OS中的AI内容合伙人，从你真实的经历、观点和旧稿出发，陪你判断值得讲什么，再一起写朋友圈、做口播。

![说明：简体中文](https://img.shields.io/badge/%E8%AF%B4%E6%98%8E-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-FFD400) [![项目：Agent Skill](https://img.shields.io/badge/%E9%A1%B9%E7%9B%AE-Agent%20Skill-FFD400)](nianxiang-content-os/SKILL.md) [![许可：MIT](https://img.shields.io/badge/%E8%AE%B8%E5%8F%AF-MIT-FFD400)](LICENSE)

[👀 看看怎么用](#-一次使用会怎样) · [🎯 适合哪些场景](#-适合哪些场景) · [🚀 安装与首次尝试](#-安装与首次尝试) · [❓ 常见问题](#-常见问题)

> 当前公开内测：**v0.1.0-beta.39** · [查看本次更新](https://github.com/KaenZhong/nianxiang-content-os/releases/tag/v0.1.0-beta.39) · MIT 开源。

## 💡 从一句真实经历开始

你可能积累了不少客户问答、分享录音和日常观察，但准备写内容时，仍会卡在这里：这段经历有什么值得讲？该选哪个切口？写出来为什么又不像自己？

你可以把这些材料交给阿响。不必先填写完整简报，也不必先搭建知识库。先聊清楚值得表达的判断；需要出稿时，再把现场、原因和观点组织成内容。

如果你希望长期协作，可以按需连接个人内容知识库，让已经确认的定位、风格、作品与方法成为后续共创的依据。

## 👀 一次使用会怎样

![共创流程：提供素材 → 判断切口 → 选择方向 → 共创内容 → 按授权保存](nianxiang-content-os/assets/readme/workflow.svg)

*这是使用流程示意，不是真实案例或执行回执。你也可以从改稿、转口播等中间步骤开始。*

先把一段经历、客户问答或分享转写粘贴给阿响：

```text
阿响，先聊聊下面这段素材值得讲什么。
面向第一次接触这个问题的人，帮我找出有价值的切口，先不用写完整稿。

[在这里粘贴你的真实素材]
```

阿响会结合材料给出判断、推荐方向和必要的事实缺口。选定后，可以继续说：

```text
阿响，用刚才选定的方向写一条朋友圈。
保留素材里的具体现场，缺少的事实先问我，不补造经历或效果。
```

有了稿件，还可以让阿响修改语气、检查表达，或改成自然口播。是否采用、是否发表以及是否保存，由你分别决定。

## 🎯 适合哪些场景

| 你的情况 | 可以直接说 | 得到什么 |
|---|---|---|
| 有经历，却不知道讲什么 | 阿响，聊聊这段经历值得讲什么。 | 素材价值判断与推荐切口 |
| 录音或转写很长，想系统挖题 | 阿响，从下面转写挖选题，展开成选题地图，我选好再写。 | 可比较的选题地图；有文档能力时优先交付飞书文档 |
| 方向明确，需要写朋友圈 | 阿响，把下面素材写成一条朋友圈，面向…… | 依据真实素材的完整初稿 |
| 已有稿，读起来不自然 | 阿响，帮我改这篇稿，保留核心判断和具体细节。 | 修改稿与必要的取舍说明 |
| 想把已有内容转成口播 | 阿响，把下面这篇稿改成自然口播。 | 适合口述的表达，无需先发表朋友圈 |
| 想让好内容持续积累 | 阿响，帮我建立个人内容知识库。 | 按实际工具与授权分批建立知识结构 |

念响OS主要支持素材讨论、选题、个人IP朋友圈和口播共创。整套活动宣传、客户宣传片、拍摄分镜等任务，需要环境中适配的专项能力。

## 🚀 安装与首次尝试

**[📦 下载 beta.39 标准Skill ZIP](https://github.com/KaenZhong/nianxiang-content-os/releases/download/v0.1.0-beta.39/nianxiang-content-os-0.1.0-beta.39.zip)** · [SHA256SUMS](https://github.com/KaenZhong/nianxiang-content-os/releases/download/v0.1.0-beta.39/SHA256SUMS) · [LICENSE](https://github.com/KaenZhong/nianxiang-content-os/releases/download/v0.1.0-beta.39/LICENSE)

把上面三个文件一起交给Agent。**[📋 复制完整安装提示词](BETA-START.md#可复制提示词)** · [全部公开内测版本](https://github.com/KaenZhong/nianxiang-content-os/releases)

1. 选择实际公开的内测发行，下载同一发行的 **标准Skill ZIP、SHA256SUMS与LICENSE**，一起交给准备使用的Agent。ZIP用于安装，SHA256SUMS用于完整性核验，LICENSE说明使用与分发许可。
2. 把[完整安装提示词](BETA-START.md#可复制提示词)发给Agent，让它检查当前平台能力、核验安装包并引导完成安装。只导入完整的 `nianxiang-content-os/` 目录。
3. 安装完成后，提供一份自己的素材，从上面的示例开始。没有私人知识库也能先共创。

已有安装应走[受控更新](nianxiang-content-os/references/maintenance/releases.md)，由Agent检查版本和现有改动。GitHub的 Source code ZIP 包含仓库外壳，不能直接作为标准受控更新包。不同平台的具体接入与限制见[三平台接入说明](nianxiang-content-os/docs/platform-setup.md)。

后续开发源码可能领先公开发行；旧版界面和说明可能仍显示旧产品名。技术标识、目录名和调用入口继续使用 `nianxiang-content-os`。

## 🌱 让共创逐渐了解你

你可以从当轮素材开始，也可以在需要时连接飞书个人内容知识库，积累：

- **定位与表达**：你服务谁、相信什么、希望怎样表达。
- **选题与作品**：候选选题、采用稿件和真实发布信息。
- **经验与方法**：服务案例、可复用的内容范式，以及经过确认的创作规则。

知识库按实际需要分批建立。保存前核对账号、对象和具体范围，保存后回读；生成稿件、采用稿件和真实发布分别记录。已有知识库先检查复用，品牌改名不会自动重命名或重建私人知识库。

[了解知识结构](nianxiang-content-os/references/knowledge/map.md) · [分批建库](nianxiang-content-os/references/knowledge/bootstrap.md) · [连接与数据归属](nianxiang-content-os/references/knowledge/connection.md)

## ❓ 常见问题

**装完就能自动记住我吗？** 需要具备相应文件与知识库能力，并完成初始化、连接和具体保存。当前对话能使用你提供的素材，不等于已经建立长期记忆。

**没有飞书能用吗？** 可以基于当轮素材讨论、写稿和改稿。长期保存与跨会话恢复取决于实际文件、账号及工具能力。

**会自动发布内容吗？** 念响OS不自带平台发布能力。稿件交付、作品保存和发布状态回填分别处理，不能把成稿当作已经发表。

**它是独立App吗？** 它是给AI助手读取和执行的Skill，需要运行在支持相应能力的Agent环境中。支持中文自然请求，也可使用 `$nianxiang-content-os` 技术入口。

**更换Agent还能接着用吗？** 需重新核验实际加载版本、账号、知识位置与可用工具。磁盘安装、当前对话读取和新会话生效分别验收，不能只凭导入成功作保证。

**能商用吗？** 公共代码与文档采用MIT许可，分发时保留许可与版权声明。你的私人知识、素材和作品不属于公开包。

## 🔒 能力边界与隐私

不补造经历、数字、身份、结果或商业承诺。工具不足或事实缺失时说明缺口；没有相应能力时，不宣称完成了知识读写、转写或跨平台操作。

公共Skill提供通用方法和占位示例。私人长期知识归飞书，连接配置、缓存和运行状态放在包外。发送材料前，请按所用AI服务的实际条件判断可提供的范围。反馈问题时也请去除私人正文、账号配置和访问凭证。

当前版本为公开内测版。离线检查不能替代真实飞书操作、独立新会话加载或跨平台完整使用验证；当前也未配置自动下载更新源（`release_source=null`）。

## 🧩 给Agent与维护者

| 入口 | 用途 |
|---|---|
| [SKILL.md](nianxiang-content-os/SKILL.md) | Agent统一入口、任务路由与执行约定 |
| [agent/](nianxiang-content-os/agent/) | 阿响的身份、气质与判断方法 |
| [references/](nianxiang-content-os/references/) | 创作方法、知识契约与系统说明 |
| [CHANGELOG.md](nianxiang-content-os/CHANGELOG.md) | 各版本具体变化与验证范围 |
| [scripts/](nianxiang-content-os/scripts/) | 知识与任务管理、结构检查和受控更新 |

维护检查（在Skill目录运行）：

```sh
python3 -B scripts/check_public_release.py
python3 -B scripts/manage.py doctor --offline
python3 -B -m unittest discover -s tests -q
```

测试使用合成资料，不代表已经验证你的生产知识库。维护规则见 [AGENTS.md](AGENTS.md)。仓库根目录的 `tools/` 仅供维护者使用，不进入用户安装包。许可见 [LICENSE](LICENSE)。

## 💬 反馈与联系

通过 [GitHub Issues](https://github.com/KaenZhong/nianxiang-content-os/issues)反馈，附上平台、版本、复现步骤、预期和实际结果，以及脱敏后的截图。

开发者：卡昂（KaenZhong） · 公众号：卡昂AI超能玩 · 反馈：kaenzhong@foxmail.com
