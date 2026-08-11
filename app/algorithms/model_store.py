"""
模型存储：使用 pickle 保存/加载 XGBoost 模型，附带元数据。
"""
import os
import pickle
import json
from typing import Any, Dict, Optional
from datetime import datetime


class ModelStore:
    def __init__(self, base_dir: str = "models"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def save_model(self, model: Any, model_name: str, meta: Dict[str, Any]) -> str:
        """保存模型和元数据，返回文件路径"""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{model_name}_{timestamp}.pkl"
        meta_filename = f"{model_name}_{timestamp}_meta.json"

        filepath = os.path.join(self.base_dir, filename)
        meta_path = os.path.join(self.base_dir, meta_filename)

        with open(filepath, 'wb') as f:
            pickle.dump(model, f)

        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

        return filepath

    def load_model(self, model_name: str) -> Optional[Any]:
        """加载最新的模型文件"""
        files = [f for f in os.listdir(self.base_dir) if f.startswith(model_name) and f.endswith('.pkl')]
        if not files:
            return None
        files.sort(key=lambda f: os.path.getmtime(os.path.join(self.base_dir, f)), reverse=True)
        latest = files[0]
        filepath = os.path.join(self.base_dir, latest)
        with open(filepath, 'rb') as f:
            return pickle.load(f)

    def load_meta(self, model_name: str) -> Optional[Dict]:
        """加载最新模型的元数据"""
        files = [f for f in os.listdir(self.base_dir) if f.startswith(model_name) and f.endswith('_meta.json')]
        if not files:
            return None
        files.sort(key=lambda f: os.path.getmtime(os.path.join(self.base_dir, f)), reverse=True)
        latest = files[0]
        meta_path = os.path.join(self.base_dir, latest)
        with open(meta_path, 'r') as f:
            return json.load(f)