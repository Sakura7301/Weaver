"""
网络搜索功能模块
"""
import requests
from datetime import datetime
from bs4 import BeautifulSoup

def fetch_webpage(url, timeout=5):
    """爬取网页并提取文本内容
    
    Args:
        url: 网页URL
        timeout: 超时时间（秒）
    
    Returns:
        str: 提取的文本内容或错误信息
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
        resp.encoding = resp.apparent_encoding
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 移除script、style等标签
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            tag.decompose()
        
        # 提取文本
        text = soup.get_text(separator='\n', strip=True)
        
        # 清理多余空行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)
        
        # 限制长度（前1500字符）
        text = text[:1500]
        
        return text
        
    except Exception as e:
        return f"爬取失败: {str(e)}"

def web_search(query, searxng_url, max_fetch=2):
    """
    搜索网络并返回结构化结果
    
    Args:
        query: 搜索关键词
        searxng_url: SearXNG服务器地址
        max_fetch: 最大爬取网页数量
    
    Returns:
        dict: 结构化搜索结果
    """
    print(f"\n🔍 正在搜索: {query}")
    
    try:
        # 调用 SearXNG
        resp = requests.get(
            f"{searxng_url}/search",
            params={"q": query, "format": "json"},
            verify=False,
            timeout=10
        )
        
        data = resp.json()
        raw_results = data.get("results", [])
        
        if not raw_results:
            print("❌ 没有搜索结果")
            return {
                "success": False,
                "query": query,
                "results": [],
                "message": "未找到相关结果"
            }
        
        print(f"✅ 找到 {len(raw_results)} 条结果")
        
        # 结构化处理
        structured_results = []
        
        for i, r in enumerate(raw_results[:5]):  # 取前5条
            result = {
                "title": r.get('title', ''),
                "url": r.get('url', ''),
                "snippet": r.get('content', '')[:200],
                "engine": ', '.join(r.get('engines', [])),
                "content": None
            }
            
            # 爬取前N个网页的内容
            if i < max_fetch:
                print(f"  📄 爬取 [{i+1}]: {result['title'][:40]}...")
                content = fetch_webpage(result['url'])
                result['content'] = content
                print(f"     ✅ 提取 {len(content)} 字符")
            
            structured_results.append(result)
        
        print(f"✅ 搜索完成，返回 {len(structured_results)} 条结构化结果\n")
        
        return {
            "success": True,
            "query": query,
            "results": structured_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        return {
            "success": False,
            "query": query,
            "results": [],
            "error": str(e)
        }