#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel Reader Skill - 读取和解析Excel文件
支持 .xlsx、.xls、.xlsm 格式，使用 xlwings 库
输出为 CSV 格式，每个工作表对应一个 CSV 文件
"""

import sys
import csv
from pathlib import Path


def check_dependencies():
    """检查依赖库是否已安装"""
    try:
        import xlwings
    except ImportError:
        print("错误: 缺少必需的库 'xlwings'")
        print("请安装: pip install xlwings")
        sys.exit(1)


class ExcelReader:
    """Excel文件读取器"""
    
    # 支持的文件格式
    SUPPORTED_FORMATS = ['.xlsx', '.xls', '.xlsm']
    
    def __init__(self, file_path: str):
        """
        初始化Excel读取器
        
        Args:
            file_path: Excel文件路径
        """
        self.file_path = Path(file_path)
        self.app = None
        self.workbook = None
        self._load()
    
    def _load(self):
        """加载Excel文件"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")
        
        # 检查文件格式
        suffix = self.file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"不支持的文件格式: {suffix}，仅支持 {', '.join(self.SUPPORTED_FORMATS)}")
        
        import xlwings as xw
        
        # 创建xlwings应用实例（不显示Excel界面）
        self.app = xw.App(visible=False)
        
        try:
            self.workbook = self.app.books.open(str(self.file_path))
        except Exception as e:
            self.app.quit()
            raise e
    
    def get_sheet_names(self) -> list:
        """
        获取所有工作表名称
        
        Returns:
            工作表名称列表
        """
        return [sheet.name for sheet in self.workbook.sheets]
    
    def get_sheet(self, sheet_name_or_index=None):
        """
        获取指定工作表
        
        Args:
            sheet_name_or_index: 工作表名称或索引，默认为第一个工作表
        
        Returns:
            工作表对象
        """
        if sheet_name_or_index is None:
            return self.workbook.sheets[0]
        elif isinstance(sheet_name_or_index, int):
            return self.workbook.sheets[sheet_name_or_index]
        else:
            return self.workbook.sheets[sheet_name_or_index]
    
    def read_sheet_raw(self, sheet_name_or_index=None) -> list:
        """
        读取工作表原始数据（二维列表）
        
        Args:
            sheet_name_or_index: 工作表名称或索引
        
        Returns:
            二维列表，每个子列表代表一行数据
        """
        sheet = self.get_sheet(sheet_name_or_index)
        
        # 获取工作表的使用范围
        used_range = sheet.used_range
        
        if used_range.rows.count == 0:
            return []
        
        # 获取所有数据
        all_data = used_range.value
        
        if not all_data:
            return []
        
        # 转换为字符串列表（CSV格式）
        result = []
        for row in all_data:
            row_data = []
            for cell in row:
                if cell is None:
                    row_data.append('')
                else:
                    row_data.append(str(cell))
            result.append(row_data)
        
        return result
    
    def to_csv(self, sheet_name_or_index=None, output_path: str = None) -> str:
        """
        将工作表数据转换为CSV格式并保存
        
        Args:
            sheet_name_or_index: 工作表名称或索引，None表示所有工作表
            output_path: 输出文件路径，None则自动生成
        
        Returns:
            保存的文件路径或文件路径列表
        """
        if sheet_name_or_index is not None:
            # 导出单个工作表
            return self._export_sheet_to_csv(sheet_name_or_index, output_path)
        else:
            # 导出所有工作表
            output_paths = []
            for idx, sheet_name in enumerate(self.get_sheet_names()):
                # 自动生成文件名
                if output_path:
                    base_path = Path(output_path)
                    sheet_output = base_path.parent / f"{base_path.stem}_{sheet_name}{base_path.suffix}"
                else:
                    sheet_output = self.file_path.parent / f"{self.file_path.stem}_{sheet_name}.csv"
                
                saved_path = self._export_sheet_to_csv(idx, str(sheet_output))
                output_paths.append(saved_path)
            
            return output_paths
    
    def _export_sheet_to_csv(self, sheet_name_or_index, output_path: str = None) -> str:
        """
        将指定工作表导出为CSV
        
        Args:
            sheet_name_or_index: 工作表名称或索引
            output_path: 输出文件路径
        
        Returns:
            保存的文件路径
        """
        sheet = self.get_sheet(sheet_name_or_index)
        sheet_name = sheet.name
        
        # 确定输出路径
        if output_path is None:
            output_path = self.file_path.parent / f"{self.file_path.stem}_{sheet_name}.csv"
        else:
            output_path = Path(output_path)
        
        # 读取数据
        data = self.read_sheet_raw(sheet_name_or_index)
        
        # 写入CSV
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(data)
        
        return str(output_path)
    
    def get_info(self) -> dict:
        """
        获取Excel文件基本信息
        
        Returns:
            包含文件信息的字典
        """
        info = {
            'file_path': str(self.file_path),
            'file_name': self.file_path.name,
            'sheet_count': len(self.get_sheet_names()),
            'sheet_names': self.get_sheet_names()
        }
        
        # 添加每个工作表的信息
        sheets_info = []
        for sheet_name in self.get_sheet_names():
            sheet = self.get_sheet(sheet_name)
            used_range = sheet.used_range
            sheets_info.append({
                'name': sheet_name,
                'row_count': used_range.rows.count,
                'col_count': used_range.columns.count
            })
        
        info['sheets'] = sheets_info
        return info
    
    def close(self):
        """关闭工作簿和Excel应用"""
        if self.workbook:
            self.workbook.close()
        if self.app:
            self.app.quit()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False


def read_excel(file_path: str) -> ExcelReader:
    """
    便捷函数，创建ExcelReader实例
    
    Args:
        file_path: Excel文件路径
    
    Returns:
        ExcelReader实例
    """
    return ExcelReader(file_path)


def main():
    """命令行入口"""
    check_dependencies()
    
    if len(sys.argv) < 2:
        print("用法: python scripts/excel_reader.py <excel文件路径> [输出目录]")
        print("示例:")
        print("  python scripts/excel_reader.py data.xlsx")
        print("  python scripts/excel_reader.py data.xlsx ./output")
        print("  python scripts/excel_reader.py data.xlsm ./output")
        sys.exit(1)
    
    file_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    reader = None
    try:
        reader = read_excel(file_path)
        
        # 显示文件信息
        info = reader.get_info()
        print(f"文件: {info['file_name']}")
        print(f"工作表数量: {info['sheet_count']}")
        for sheet_info in info['sheets']:
            print(f"  - {sheet_info['name']}: {sheet_info['row_count']} 行 x {sheet_info['col_count']} 列")
        print()
        
        # 确定输出目录
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            base_name = Path(file_path).stem
            output_file = output_path / f"{base_name}.csv"
        else:
            output_file = None
        
        # 导出所有工作表到CSV
        result = reader.to_csv(output_path=str(output_file) if output_file else None)
        
        if isinstance(result, list):
            print(f"已导出 {len(result)} 个工作表:")
            for path in result:
                print(f"  - {path}")
        else:
            print(f"已导出: {result}")
    
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)
    
    finally:
        if reader:
            reader.close()


if __name__ == '__main__':
    main()
