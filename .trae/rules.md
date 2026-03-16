# YDem Skills 项目规则

## 必须做

1. **Skill 目录结构**
   - 脚本必须放在 `scripts/` 子目录下
   - 必须包含 `SKILL.md` 使用说明文档

2. **引用路径**
   - 模块导入使用绝对路径：`from <分类>.<skill_name> import <功能>`
   - 命令行使用相对路径：`python scripts/<script>.py`

3. **Python 执行**
   - 使用 `python` 命令
   - 不指定 Python 绝对路径

## 不能做

1. **禁止擅自安装 Python 库** - 缺少库时提醒用户手动安装
2. **不要使用系统 Python** - 使用环境默认的 python 命令
3. **禁止在 Skill 目录中使用 `__init__.py`** - 直接导入 `scripts` 下的模块
