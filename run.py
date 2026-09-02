from app.main import create_app
import uvicorn

# P1-08: 禁用旧 EMSService 后台循环，避免双控制链冲突
app = create_app(start_background=False)

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=False)