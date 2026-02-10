# Auto_Class_Assigner

一个自动分班工具，基于蛇形排列与启发式算法，综合考虑尖子生分布与各科成绩均衡。



### 使用方法

**本地部署**
若从源码本地部署，推荐使用conda:
```bash
conda create -n aca python==3.10 -y
conda activate aca
python -m uvicorn app.main:app --reload --port 8000
```
之后，可以从`http://localhost:8000`访问并使用。