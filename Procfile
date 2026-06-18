web: uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
paper: python paper_trader.py
audit: python audit_runner.py --follow --candidates --interval 604800
