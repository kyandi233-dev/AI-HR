"""Reserved for resume ability measurement; no scale has been selected yet."""
import argparse


def main():
    parser=argparse.ArgumentParser(description='实验2：简历能力独立评价。指标与提示词尚未确定，目前不能采集数据。')
    parser.parse_args()
    parser.error('尚未定义简历能力评价指标；resume-review 是质量审核，不能代替本任务。')


if __name__=='__main__':
    main()
