# Excel Reader Skill 使用说明

## 简介

`excel_reader.py` 是一个用于读取和解析 Excel 文件（.xlsx、.xls、.xlsm 格式）的 Python Skill。它将 Excel 数据导出为 CSV 格式，每个工作表对应一个 CSV 文件。

本 Skill 使用 **xlwings** 库，提供了强大的 Excel 操作能力。

## 环境要求

- Python 3.6+
- xlwings 库（已安装）
- Microsoft Excel 或 WPS Office（系统中已安装）

**注意**: xlwings 依赖 Microsoft Excel 或 WPS Office，请确保系统中已安装。

## 支持的文件格式

- `.xlsx` - Excel 2007+ 格式
- `.xls` - Excel 97-2003 格式
- `.xlsm` - Excel 启用宏的工作簿（宏会被忽略，只读取数据）

## 使用方法

### 1. 作为模块导入使用（推荐）

```python
from scripts.excel_reader import read_excel

# 读取 Excel 文件
reader = read_excel('data.xlsx')

# 获取文件信息
info = reader.get_info()
print(f"工作表: {info['sheet_names']}")

# 导出所有工作表为 CSV（每个工作表一个文件）
output_paths = reader.to_csv()
print(f"已导出: {output_paths}")

# 导出指定工作表为 CSV
output_path = reader.to_csv('Sheet2', 'output.csv')
print(f"已导出: {output_path}")

# 使用完毕后关闭（或使用上下文管理器）
reader.close()
```

**使用上下文管理器（推荐）：**

```python
from scripts.excel_reader import read_excel

with read_excel('data.xlsx') as reader:
    # 导出所有工作表
    output_paths = reader.to_csv()
    # 处理...
# 自动关闭 Excel 进程
```

### 2. 命令行使用

```bash
# 查看文件信息并导出所有工作表到当前目录
python scripts/excel_reader.py data.xlsx

# 导出到指定目录
python scripts/excel_reader.py data.xlsx ./output

# 支持 xlsm 文件
python scripts/excel_reader.py data.xlsm ./output
```

### 3. API 方法

#### `read_excel(file_path)`

便捷函数，返回 `ExcelReader` 实例。

#### `ExcelReader` 类方法

- **`get_sheet_names()`** - 获取所有工作表名称列表
- **`get_sheet(sheet_name_or_index=None)`** - 获取指定工作表对象
- **`read_sheet_raw(sheet_name_or_index=None)`** - 读取工作表原始数据，返回二维列表
- **`to_csv(sheet_name_or_index=None, output_path=None)`** - 导出为 CSV 文件
  - `sheet_name_or_index`: 工作表名称或索引，`None` 表示导出所有工作表
  - `output_path`: 输出文件路径，`None` 则自动生成
- **`get_info()`** - 获取 Excel 文件基本信息
- **`close()`** - 关闭工作簿和 Excel 应用（使用上下文管理器时自动调用）

### 4. 使用示例

```python
from scripts.excel_reader import read_excel

# 读取文件
reader = read_excel('data.xlsx')

try:
    # 获取文件信息
    info = reader.get_info()
    print(f"文件名: {info['file_name']}")
    print(f"工作表数量: {info['sheet_count']}")
    for sheet in info['sheets']:
        print(f"  - {sheet['name']}: {sheet['row_count']} 行 x {sheet['col_count']} 列")

    # 导出所有工作表（自动生成文件名：原文件名_工作表名.csv）
    output_paths = reader.to_csv()
    for path in output_paths:
        print(f"已保存: {path}")

    # 导出指定工作表
    output_path = reader.to_csv('Sheet2', 'sheet2_data.csv')
    print(f"已保存: {output_path}")

    # 读取原始数据
    raw_data = reader.read_sheet_raw('Sheet1')
    for row in raw_data[:5]:  # 显示前5行
        print(row)
finally:
    # 确保关闭 Excel 进程
    reader.close()
```

## 输出格式

### CSV 文件

每个工作表导出为一个 CSV 文件，文件名格式为：`{原文件名}_{工作表名}.csv`

**示例：**
- 原文件：`data.xlsx`
- 包含工作表：`Sheet1`、`Sheet2`
- 输出文件：`data_Sheet1.csv`、`data_Sheet2.csv`

### CSV 格式特点

- 使用 UTF-8 with BOM 编码（兼容 Excel 中文显示）
- 所有数据转换为字符串格式
- 空单元格转换为空字符串
- 使用标准 CSV 格式（逗号分隔）

## 注意事项

1. **Excel 进程**: xlwings 会启动 Excel 进程，使用完毕后务必调用 `close()` 方法或使用上下文管理器，否则 Excel 进程会继续运行。

2. **xlsm 文件**: 启用宏的工作簿中的宏会被忽略，只读取数据。

3. **数据类型**: 所有数据导出为字符串格式，保持原始显示内容。

4. **大文件处理**: 对于大型 Excel 文件，建议分工作表处理。

## 示例

假设有一个 `sample.xlsx` 文件，包含两个工作表 `Sheet1` 和 `Sheet2`：

```bash
# 导出到当前目录
python scripts/excel_reader.py sample.xlsx

# 输出:
# 文件: sample.xlsx
# 工作表数量: 2
#   - Sheet1: 100 行 x 5 列
#   - Sheet2: 50 行 x 3 列
#
# 已导出 2 个工作表:
#   - sample_Sheet1.csv
#   - sample_Sheet2.csv
```
