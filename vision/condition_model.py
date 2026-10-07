"""Person 2 - condition scoring.

Labels CSV columns: image_path, condition_score (1-10), crease, tear, scratch, seal_broken (0/1)

  python -m vision.condition_model train labels.csv
  python -m vision.condition_model score_db          # fills condition_score IS NULL rows
"""
import sys
import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms as T

from common.db import connect

DEFECTS = ["crease", "tear", "scratch", "seal_broken"]
WEIGHTS = "vision/condition_model.pt"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
NORM = T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])

eval_tf = T.Compose([T.Resize(256), T.CenterCrop(224), T.ToTensor(), NORM])
train_tf = T.Compose([T.Resize(256), T.RandomResizedCrop(224, scale=(0.8, 1.0)),
                      T.ColorJitter(0.2, 0.2, 0.1), T.ToTensor(), NORM])


def load_image(src) -> Image.Image:
    """src = path or raw bytes. Decodes, light denoise (edge-preserving), returns RGB PIL image."""
    buf = np.frombuffer(src, np.uint8) if isinstance(src, (bytes, bytearray)) else np.fromfile(src, np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    img = cv2.bilateralFilter(img, d=5, sigmaColor=40, sigmaSpace=40)
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


class ConditionNet(nn.Module):
    """ResNet-50 backbone -> (continuous score in [1,10], multi-label defect logits)."""

    def __init__(self, pretrained=True):
        super().__init__()
        self.backbone = models.resnet50(weights=models.ResNet50_Weights.DEFAULT if pretrained else None)
        n = self.backbone.fc.in_features
        self.backbone.fc = nn.Identity()
        self.score_head = nn.Sequential(nn.Dropout(0.2), nn.Linear(n, 1))
        self.defect_head = nn.Sequential(nn.Dropout(0.2), nn.Linear(n, len(DEFECTS)))

    def forward(self, x):
        f = self.backbone(x)
        score = 1 + 9 * torch.sigmoid(self.score_head(f)).squeeze(1)
        return score, self.defect_head(f)


class LabelledImages(Dataset):
    def __init__(self, df, tf):
        self.df, self.tf = df.reset_index(drop=True), tf

    def __len__(self):
        return len(self.df)

    def __getitem__(self, i):
        r = self.df.iloc[i]
        x = self.tf(load_image(r.image_path))
        return (x, torch.tensor(r.condition_score, dtype=torch.float32),
                torch.tensor(r[DEFECTS].values.astype(np.float32)))


def train(csv_path, epochs=12, batch=32):
    df = pd.read_csv(csv_path).sample(frac=1, random_state=0)
    cut = int(0.85 * len(df))
    tr = DataLoader(LabelledImages(df[:cut], train_tf), batch, shuffle=True, num_workers=2)
    va = DataLoader(LabelledImages(df[cut:], eval_tf), batch, num_workers=2)

    model = ConditionNet().to(DEVICE)
    opt = torch.optim.AdamW([{"params": model.backbone.parameters(), "lr": 1e-4},
                             {"params": list(model.score_head.parameters()) +
                                        list(model.defect_head.parameters()), "lr": 1e-3}], weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    huber, bce = nn.SmoothL1Loss(), nn.BCEWithLogitsLoss()
    best = 1e9

    for ep in range(epochs):
        model.train()
        for x, y, d in tr:
            x, y, d = x.to(DEVICE), y.to(DEVICE), d.to(DEVICE)
            s, logits = model(x)
            loss = huber(s, y) + 0.5 * bce(logits, d)
            opt.zero_grad(); loss.backward(); opt.step()
        sched.step()

        model.eval(); mae = n = 0
        with torch.no_grad():
            for x, y, _ in va:
                s, _ = model(x.to(DEVICE))
                mae += (s.cpu() - y).abs().sum().item(); n += len(y)
        mae /= n
        print(f"epoch {ep+1}/{epochs}  val MAE={mae:.3f}")
        if mae < best:
            best = mae
            torch.save(model.state_dict(), WEIGHTS)
    print(f"best val MAE {best:.3f} -> {WEIGHTS}")


_model = None


def _get_model():
    global _model
    if _model is None:
        _model = ConditionNet(pretrained=False)
        _model.load_state_dict(torch.load(WEIGHTS, map_location=DEVICE))
        _model.to(DEVICE).eval()
    return _model


@torch.no_grad()
def predict_condition(image_bytes: bytes) -> dict:
    """-> {"condition_score": float, "defects": list[str]}"""
    x = eval_tf(load_image(image_bytes)).unsqueeze(0).to(DEVICE)
    s, logits = _get_model()(x)
    probs = torch.sigmoid(logits)[0].cpu().numpy()
    return {"condition_score": round(float(s.item()), 2),
            "defects": [d for d, p in zip(DEFECTS, probs) if p > 0.5]}


def score_db(db_path=None, commit_every=50):
    """Batch job: fill condition_score for every row where it IS NULL."""
    conn = connect(db_path)
    rows = conn.execute("SELECT listing_id, image_path FROM listings "
                        "WHERE condition_score IS NULL AND image_path IS NOT NULL").fetchall()
    for i, (lid, path) in enumerate(rows, 1):
        try:
            with open(path, "rb") as f:
                score = predict_condition(f.read())["condition_score"]
            conn.execute("UPDATE listings SET condition_score=? WHERE listing_id=?", (score, lid))
        except Exception as e:
            print(f"skip {lid}: {e}")
        if i % commit_every == 0:
            conn.commit()
    conn.commit()
    print(f"scored {len(rows)} listings")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "train":
        train(sys.argv[2])
    elif cmd == "score_db":
        score_db()
    else:
        print(__doc__)
