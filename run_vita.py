#!/usr/bin/env python
# VITA 启动脚本
import os
import subprocess

# 设置环境变量
os.environ['VITA_DB_USER'] = 'maxsearch'
os.environ['VITA_DB_PASSWORD'] = 'sZ36!mTrBxH'
os.environ['VITA_DB_DSN'] = '10.97.4.7:1521/eamprod'
os.environ['VITA_ORACLE_CLIENT'] = 'D:/instantclient/instantclient_23_9'
os.environ['VITA_LLM_URL'] = 'http://10.96.158.22:8000/v1'
os.environ['VITA_LLM_KEY'] = 'hebz9jMiWwkqiV2NTDE1AiBEKj_Sz0Ga'
os.environ['VITA_LLM_MODEL'] = 'gemma-4-31b-it'
os.environ['VITA_LLM_FALLBACK_URL'] = 'http://10.96.158.22:8000/v1'
os.environ['VITA_LLM_FALLBACK_KEY'] = 'hebz9jMiWwkqiV2NTDE1AiBEKj_Sz0Ga'
os.environ['VITA_LLM_FALLBACK_MODEL'] = 'gemma-4-31b-it'
os.environ['VITA_EMBEDDING_URL'] = 'http://10.98.12.69:8080/embed'
os.environ['VITA_RERANK_URL'] = 'http://10.98.12.69:8081/rerank'

# 启动Streamlit
subprocess.run([
    'python', '-m', 'streamlit', 'run', 'vita.py',
    '--server.port', '8501',
    '--server.address', 'localhost'
], cwd=r'E:\vita')
