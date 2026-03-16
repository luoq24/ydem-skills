"""
XMind文件读取器 Skill
用于读取和解析.xmind文件，提取思维导图内容
"""

import zipfile
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class XMindReader:
    """XMind文件读取器"""
    
    def __init__(self, file_path: str):
        """
        初始化XMind读取器
        
        Args:
            file_path: xmind文件路径
        """
        self.file_path = Path(file_path)
        self.data = None
        self._validate_file()
    
    def _validate_file(self):
        """验证文件是否存在且为有效的xmind文件"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")
        
        if not self.file_path.suffix.lower() == '.xmind':
            raise ValueError(f"文件必须是.xmind格式: {self.file_path}")
    
    def load(self) -> Dict[str, Any]:
        """
        加载并解析xmind文件
        
        Returns:
            解析后的数据结构
        """
        try:
            with zipfile.ZipFile(self.file_path, 'r') as zf:
                # 读取content.json
                if 'content.json' in zf.namelist():
                    content = zf.read('content.json').decode('utf-8')
                    self.data = json.loads(content)
                else:
                    raise ValueError("无效的xmind文件：缺少content.json")
        except zipfile.BadZipFile:
            raise ValueError("文件不是有效的zip/xmind格式")
        
        return self.data
    
    def get_sheets(self) -> List[Dict[str, Any]]:
        """
        获取所有工作表(sheet)
        
        Returns:
            工作表列表
        """
        if self.data is None:
            self.load()
        return self.data if isinstance(self.data, list) else [self.data]
    
    def get_root_topic(self, sheet_index: int = 0) -> Optional[Dict[str, Any]]:
        """
        获取指定工作表的根主题
        
        Args:
            sheet_index: 工作表索引，默认为0
            
        Returns:
            根主题数据
        """
        sheets = self.get_sheets()
        if sheet_index < len(sheets):
            return sheets[sheet_index].get('rootTopic')
        return None
    
    def _decode_title(self, title: str) -> str:
        """解码标题，处理可能的编码问题"""
        if title is None:
            return ""
        # Python 3中json.loads()已经正确解码UTF-8，无需额外处理
        return str(title)
    
    def extract_topic_tree(self, topic: Dict[str, Any], level: int = 0) -> List[Dict[str, Any]]:
        """
        递归提取主题树结构
        
        Args:
            topic: 主题数据
            level: 当前层级
            
        Returns:
            扁平化的主题列表
        """
        result = []
        
        if topic is None:
            return result
        
        # 提取当前主题信息
        raw_title = topic.get('title', '')
        topic_info = {
            'level': level,
            'title': self._decode_title(raw_title),
            'id': topic.get('id', ''),
            'class': topic.get('class', ''),
            'children_count': 0
        }
        
        # 获取子主题
        children = []
        if 'children' in topic and 'attached' in topic['children']:
            children = topic['children']['attached']
            topic_info['children_count'] = len(children)
        
        result.append(topic_info)
        
        # 递归处理子主题
        for child in children:
            result.extend(self.extract_topic_tree(child, level + 1))
        
        return result
    
    def to_markdown(self, sheet_index: int = 0) -> str:
        """
        将思维导图转换为Markdown格式
        
        Args:
            sheet_index: 工作表索引，默认为0
            
        Returns:
            Markdown格式的字符串
        """
        root = self.get_root_topic(sheet_index)
        if root is None:
            return ""
        
        topics = self.extract_topic_tree(root)
        lines = []
        
        for topic in topics:
            indent = "  " * topic['level']
            title = topic['title'] or '(无标题)'
            lines.append(f"{indent}- {title}")
        
        return "\n".join(lines)
    
    def to_dict(self, sheet_index: int = 0) -> Dict[str, Any]:
        """
        获取完整的数据字典
        
        Args:
            sheet_index: 工作表索引，默认为0
            
        Returns:
            包含所有信息的字典
        """
        root = self.get_root_topic(sheet_index)
        if root is None:
            return {}
        
        return {
            'file_path': str(self.file_path),
            'sheet_title': self.get_sheets()[sheet_index].get('title', ''),
            'topics': self.extract_topic_tree(root),
            'raw_data': root
        }
    
    def search(self, keyword: str, sheet_index: int = 0) -> List[Dict[str, Any]]:
        """
        搜索包含关键词的主题
        
        Args:
            keyword: 搜索关键词
            sheet_index: 工作表索引，默认为0
            
        Returns:
            匹配的主题列表
        """
        root = self.get_root_topic(sheet_index)
        if root is None:
            return []
        
        topics = self.extract_topic_tree(root)
        results = []
        
        for topic in topics:
            if keyword.lower() in topic['title'].lower():
                results.append(topic)
        
        return results


def read_xmind(file_path: str) -> XMindReader:
    """
    便捷函数：读取xmind文件
    
    Args:
        file_path: xmind文件路径
        
    Returns:
        XMindReader实例
        
    Example:
        >>> reader = read_xmind('example.xmind')
        >>> print(reader.to_markdown())
    """
    return XMindReader(file_path)


# 命令行接口
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python xmind_reader.py <xmind文件路径> [输出文件路径]")
        sys.exit(1)
    
    file_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        reader = read_xmind(file_path)
        markdown = reader.to_markdown()
        
        if output_path:
            # 保存到文件（UTF-8编码）
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown)
            print(f"已保存到: {output_path}")
        else:
            # 输出到控制台
            print(markdown)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)
