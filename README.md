# 念响内容OS开发仓库

完整产品名为“念响AI · 内容OS”，简称“念响内容OS”。此本地 Git 仓库是公共开发源；`nianxiang-content-os/` 是可导入的公共 Skill 包。仓库管理文件与 `.git/` 不进入交付包或 Skill 安装目录。

## 版本记录

从已保留且逐文件核验通过的公共发行包导入 `v0.1.0-beta.2` 至 `v0.1.0-beta.5`。这些提交是历史发行快照导入，不是对原始开发提交或开发时间的重建；没有可核验首版完整包，因此不补造 beta.1 标签。之后按实际维护提交记录，验收后的发行使用不可改写的版本标签。

## 日常维护

在本仓库修改公共源，检查差异并提交；发行时更新版本、CHANGELOG 与发行清单，验证后提交并加版本标签。将已核验的 `nianxiang-content-os/` 同步到既有最终交付目录和运行安装。目录路径属于本机部署登记，保存于不被 Git 跟踪的 `.git/nianxiang-deployment.json`。

Git 保存公共版本历史；当前安装只留最近一次必要的实体回退点。更早公共核心副本须与对应 Git 标签逐文件核对后才清理，安装回执保留并登记还原标签。旧 Skill 中的私人原件、其他产品备份以及未完成的安装事务不清理。历史回退从所选标签导出公共子目录、验包，并在具体授权后切换；不在开发源上强制重置，也不将私人数据回滚到历史版本。

## 检查

```sh
python3 -B nianxiang-content-os/scripts/check_public_release.py
python3 -B nianxiang-content-os/scripts/manage.py doctor --offline
git status --short
```

公共包检查与安装切换规则见 [公共核心更新](nianxiang-content-os/references/maintenance/releases.md)。当前仓库只有本地 Git 历史，尚未配置远端或正式公开发布；许可证与发布位置另行落实。本地 Git 仓库并不能抵御整台电脑丢失。
