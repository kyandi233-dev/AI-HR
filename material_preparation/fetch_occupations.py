"""下载职业来源并保存原文，不自动批准材料。"""
# 直接运行脚本时，将项目根目录加入模块查找路径。
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import json
from shared import common as c
from shared.common import job_files, now, sha256

def fetch_onet(args,occ):
    if args.occupation not in occ: raise ValueError('未知职业')
    code=occ[args.occupation]['onet_code']
    url=f'https://www.onetonline.org/link/details/{code}'
    folder=job_files(args.occupation)['source']
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
    if not text:
        raise RuntimeError('职业网页正文为空：'+url)
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'source_details.html').write_text(resp.text,encoding='utf-8')
    (folder/'source_details.txt').write_text(text,encoding='utf-8')
    meta={'url':url,'retrieved_utc':now(),'status_code':resp.status_code,
          'sha256_html':sha256(resp.content),'sha256_text':sha256(text),
          'source':'O*NET OnLine','researcher_reviewed':False}
    (folder/'source_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('抓取成功：', (folder/'source_details.txt').relative_to(c.ROOT))
    print('请人工审核，并将职业资料保存到 material_preparation/approved/occupations/<职业ID>/onet/profile.txt。')


if __name__=='__main__':
    import argparse
    import sys
    parser=argparse.ArgumentParser(description='获取职业来源；默认预览，不调用模型')
    parser.add_argument('--occupation',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    try:
        fetch_onet(args,c.load_json(c.occupations_file()))
    except Exception as exc:
        print('失败：'+str(exc),file=sys.stderr)
        sys.exit(2)
