"""Download source pages without treating them as approved materials."""
import json
from . import common as c
from .common import job_files, now, sha256

def fetch_onet(args,occ):
    if args.occupation not in occ: raise ValueError('未知职业')
    code=occ[args.occupation]['onet_code']
    url=f'https://www.onetonline.org/link/details/{code}'
    folder=job_files(args.occupation)['profile'].parent
    if not args.execute:
        print('预览：将从 O*NET 唯一来源下载',url)
        print('只保存 source_details.html、source_details.txt、source_metadata.json；需人工确认再复制为 profile.txt')
        return
    import requests
    from bs4 import BeautifulSoup
    resp=requests.get(url,timeout=45,headers={'User-Agent':'Mozilla/5.0 (compatible; Academic research download)'})
    resp.raise_for_status()
    soup=BeautifulSoup(resp.text,'html.parser')
    for tag in soup(['script','style','nav','footer']): tag.decompose()
    body=soup.find('main') or soup.find(id='content') or soup.body or soup
    text=body.get_text('\n',strip=True)
    if len(text)<800:
        raise RuntimeError('页面抓取结果过短，可能被访问限制；请手工从 O*NET 复制资料')
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'source_details.html').write_text(resp.text,encoding='utf-8')
    (folder/'source_details.txt').write_text(text,encoding='utf-8')
    meta={'url':url,'retrieved_utc':now(),'status_code':resp.status_code,
          'sha256_html':sha256(resp.content),'sha256_text':sha256(text),
          'source':'O*NET OnLine','researcher_reviewed':False}
    (folder/'source_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('抓取成功：', (folder/'source_details.txt').relative_to(c.ROOT))
    print('请阅读内容、保留有效职业栏目，并将审查后的文字保存为 onet/profile.txt。')
