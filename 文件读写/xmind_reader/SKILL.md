# XMind Reader Skill 使用说明

## 简介

`xmind_reader.py` 是一个用于读取和解析 `.xmind` 文件的 Python Skill。它可以将思维导图转换为 Markdown 格式，方便进一步处理和分析。

## 安装

无需额外安装，只需要 Python 3.6+ 环境。

## 使用方法

### 1. 作为模块导入使用（推荐）

```python
from scripts.xmind_reader import read_xmind

# 读取 xmind 文件
reader = read_xmind('花火大会2期.xmind')

# 转换为 Markdown 格式
markdown = reader.to_markdown()

# 保存到文件（推荐方式，避免控制台编码问题）
with open('output.md', 'w', encoding='utf-8') as f:
    f.write(markdown)
print('内容已保存到 output.md')
```

### 2. 命令行使用

```bash
# 输出到控制台（Windows 控制台可能显示乱码）
python scripts/xmind_reader.py "花火大会2期.xmind"

# 保存到文件（推荐）
python scripts/xmind_reader.py "花火大会2期.xmind" output.md
```

### 3. API 方法

#### `read_xmind(file_path)`
便捷函数，返回 `XMindReader` 实例。

#### `XMindReader` 类方法

- **`load()`** - 加载并解析 xmind 文件
- **`get_sheets()`** - 获取所有工作表(sheet)
- **`get_root_topic(sheet_index=0)`** - 获取指定工作表的根主题
- **`to_markdown(sheet_index=0)`** - 将思维导图转换为 Markdown 格式
- **`to_dict(sheet_index=0)`** - 获取完整的数据字典
- **`search(keyword, sheet_index=0)`** - 搜索包含关键词的主题

### 4. 使用示例

```python
from scripts.xmind_reader import read_xmind

# 读取文件
reader = read_xmind('花火大会2期.xmind')

# 获取所有主题列表
topics = reader.extract_topic_tree(reader.get_root_topic())
for topic in topics:
    print(f"{'  ' * topic['level']}- {topic['title']}")

# 搜索特定关键词
results = reader.search('花火')
for result in results:
    print(f"找到: {result['title']} (层级: {result['level']})")

# 获取完整数据结构
data = reader.to_dict()
print(f"文件路径: {data['file_path']}")
print(f"工作表标题: {data['sheet_title']}")
print(f"主题数量: {len(data['topics'])}")
```

## 输出格式

### Markdown 格式示例

```markdown
- 花火大会2期
  - 花火大会2期
    - 组队逻辑
      - 角名+北信介的循环
        - 北信介守护天才们成长，天才觉醒后通过极致的表演将球队带往更高处。
        - 角名启动慢
          - 北信介加速启动
            - 角名启动反哺北信介
              - 北信介转化成全队增益
      - 队伍构成
        - 角名伦太郎
          - 副拦网，主扣球
          - 前期拦网暖机，后期扣球爆发
        ...
```

### 数据结构

每个主题包含以下信息：
- `level`: 层级（0为根主题）
- `title`: 标题文本
- `id`: 主题唯一标识
- `class`: 主题类型
- `children_count`: 子主题数量

## 注意事项

1. **编码问题**: xmind 文件使用 UTF-8 编码，本 Skill 已正确处理。如果在 Windows 控制台看到乱码，这是控制台编码问题（Windows 默认使用 GBK），不影响文件保存的正确性。**建议始终将输出保存到文件**。

2. **文件格式**: 支持 XMind 2020/2021/2022 版本创建的 `.xmind` 文件。

3. **多工作表**: 如果 xmind 文件包含多个工作表(sheet)，可以通过 `sheet_index` 参数指定要读取的工作表。

## 常见问题与解决方案

### 问题: Windows 控制台输出中文乱码

**现象**: 在 Windows 命令行中运行 `python xmind_reader.py` 时，中文字符显示为乱码。

**原因**: Windows 控制台默认使用 GBK 编码，而 Python 输出使用 UTF-8 编码，导致编码不匹配。

**解决方案**: **始终将输出保存到文件**

```python
from scripts.xmind_reader import read_xmind

reader = read_xmind('花火大会2期.xmind')
markdown = reader.to_markdown()

# 保存到文件，避免控制台编码问题
with open('output.md', 'w', encoding='utf-8') as f:
    f.write(markdown)
print('内容已保存到 output.md')  # 这行可能显示乱码，但不影响文件内容
```

命令行方式：
```bash
python scripts/xmind_reader.py "花火大会2期.xmind" output.md
```

## 示例文件

测试文件: `花火大会2期.xmind`

运行测试:
```bash
python scripts/xmind_reader.py "花火大会2期.xmind" output_xmind_utf8.md
```

这将生成 `output_xmind_utf8.md` 文件，包含转换后的 Markdown 内容。
