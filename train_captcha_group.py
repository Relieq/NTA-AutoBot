import json
import os
import random

import torch
import torch.nn as nn
import torch.optim as optim
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms


GROUPS = [
    "Linh Thuong",
    "Linh Khien",
    "Linh Cung",
    "Linh Ky",
    "Khi Gioi",
    "Da Thu",
]

CLASS_TO_GROUP = {
    "linh_mach_dao": "Linh Thuong",
    "linh_song_thuong": "Linh Thuong",
    "linh_truong_giao": "Linh Thuong",
    "linh_truong_kiem": "Linh Thuong",
    "linh_truong_mau": "Linh Thuong",
    "linh_truong_thuong": "Linh Thuong",

    "linh_bua_khien": "Linh Khien",
    "linh_dao_khien": "Linh Khien",
    "linh_kiem_khien": "Linh Khien",
    "linh_khien_lon": "Linh Khien",
    "linh_riu_khien": "Linh Khien",
    "linh_thuong_khien": "Linh Khien",

    "linh_cung_doc": "Linh Cung",
    "linh_cung_lua": "Linh Cung",
    "linh_cuong_no": "Linh Cung",
    "linh_lien_no": "Linh Cung",
    "linh_truong_cung": "Linh Cung",
    "tho_san": "Linh Cung",

    "linh_cung_ky": "Linh Ky",
    "linh_dao_ky": "Linh Ky",
    "linh_kiem_ky": "Linh Ky",
    "linh_riu_ky": "Linh Ky",
    "linh_thuong_ky": "Linh Ky",
    "linh_trong_ky": "Linh Ky",

    "xe_nem_da": "Khi Gioi",
    "xe_no_lon": "Khi Gioi",

    "chon_hoi": "Da Thu",
    "gau": "Da Thu",
    "nhim": "Da Thu",
    "voi": "Da Thu",
    "soi_hoang": "Da Thu",
    "bao_san": "Da Thu",
    "heo_rung": "Da Thu",
    "bumblebee": "Da Thu",
    "than_lan": "Da Thu",
    "lao_ho": "Da Thu",
    "bo_rung": "Da Thu",
}


class BaseGroupCaptchaDataset(Dataset):
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.group_to_idx = {name: i for i, name in enumerate(GROUPS)}
        self.samples = []
        self.group_samples = {group: [] for group in GROUPS}

        class_dirs = sorted([d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d))])
        for cls_name in class_dirs:
            group_name = CLASS_TO_GROUP.get(cls_name)
            if group_name is None:
                continue
            group_idx = self.group_to_idx[group_name]
            cls_dir = os.path.join(root_dir, cls_name)

            for file_name in sorted(os.listdir(cls_dir)):
                if file_name.lower().endswith((".png", ".jpg", ".jpeg")):
                    sample = (os.path.join(cls_dir, file_name), group_idx)
                    self.samples.append(sample)
                    self.group_samples[group_name].append(sample)

        if not self.samples:
            raise RuntimeError("Group dataset is empty")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = Image.open(img_path).convert("RGB")
        return img, label


class AugmentedDataset(Dataset):
    def __init__(self, base_dataset, transform, epoch_size, random_sample=True):
        self.base_dataset = base_dataset
        self.transform = transform
        self.epoch_size = epoch_size
        self.random_sample = random_sample

    def __len__(self):
        return self.epoch_size

    def __getitem__(self, idx):
        if self.random_sample:
            base_idx = random.randint(0, len(self.base_dataset) - 1)
        else:
            base_idx = idx % len(self.base_dataset)

        img, label = self.base_dataset[base_idx]
        if self.transform:
            img = self.transform(img)
        return img, label


class BalancedGroupAugmentedDataset(Dataset):
    """Sinh dữ liệu ảo cân bằng theo GROUP để tránh bias nặng về Da Thu."""

    def __init__(self, base_dataset, transform, epoch_size):
        self.base_dataset = base_dataset
        self.transform = transform
        self.epoch_size = epoch_size
        self.active_groups = [g for g in GROUPS if len(base_dataset.group_samples.get(g, [])) > 0]

        if not self.active_groups:
            raise RuntimeError("No active group in dataset")

    def __len__(self):
        return self.epoch_size

    def __getitem__(self, idx):
        # Chọn group đồng đều, rồi random sample trong group đó.
        group_name = self.active_groups[idx % len(self.active_groups)]
        samples = self.base_dataset.group_samples[group_name]
        img_path, label = random.choice(samples)
        img = Image.open(img_path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, label


def set_seed(seed=42):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def evaluate(model, dataloader, criterion, device):
    model.eval()
    running_loss = 0.0
    total = 0
    correct = 0

    with torch.no_grad():
        for x, y in dataloader:
            x, y = x.to(device), y.to(device)
            out = model(x)
            loss = criterion(out, y)
            running_loss += float(loss.item()) * x.size(0)
            pred = torch.argmax(out, dim=1)
            correct += int((pred == y).sum().item())
            total += int(y.size(0))

    return running_loss / max(total, 1), correct / max(total, 1)


def main():
    set_seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    train_tf = transforms.Compose([
        transforms.Resize((64, 64)),
        transforms.RandomRotation(18),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomAffine(degrees=0, translate=(0.06, 0.06), scale=(0.92, 1.08)),
        transforms.ColorJitter(brightness=0.12, contrast=0.12, saturation=0.06, hue=0.02),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    val_tf = transforms.Compose([
        transforms.Resize((64, 64)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    base = BaseGroupCaptchaDataset("dataset")
    train_size = max(7200, len(base) * 180)
    val_size = max(2400, len(base) * 60)

    train_ds = BalancedGroupAugmentedDataset(base, train_tf, train_size)
    # Val giữ sampling thường để phản ánh phân bố tự nhiên tốt hơn.
    val_ds = AugmentedDataset(base, val_tf, val_size, random_sample=False)

    pin_memory = torch.cuda.is_available()
    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True, num_workers=0, pin_memory=pin_memory)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False, num_workers=0, pin_memory=pin_memory)

    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.last_channel, len(GROUPS))
    model = model.to(device)

    # Class-weight theo nghịch đảo tần suất group trong ảnh gốc.
    group_counts = {name: len(base.group_samples.get(name, [])) for name in GROUPS}
    weights = []
    for group_name in GROUPS:
        c = max(group_counts[group_name], 1)
        weights.append(1.0 / float(c))
    weights_tensor = torch.tensor(weights, dtype=torch.float32, device=device)
    weights_tensor = weights_tensor / weights_tensor.sum() * len(GROUPS)

    criterion = nn.CrossEntropyLoss(weight=weights_tensor)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

    best_state = None
    best_acc = -1.0
    best_epoch = -1
    epochs = 15

    print(f"Base samples: {len(base)} | train_size={len(train_ds)} val_size={len(val_ds)}")
    print(f"Groups: {GROUPS}")
    print(f"Group counts: {group_counts}")
    print(f"Class weights: {[round(float(x), 4) for x in weights_tensor.detach().cpu().tolist()]}")

    for epoch in range(epochs):
        model.train()
        run_loss = 0.0
        run_total = 0
        run_correct = 0

        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()

            run_loss += float(loss.item()) * x.size(0)
            pred = torch.argmax(out, dim=1)
            run_correct += int((pred == y).sum().item())
            run_total += int(y.size(0))

        train_loss = run_loss / max(run_total, 1)
        train_acc = run_correct / max(run_total, 1)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        scheduler.step(val_acc)

        lr = optimizer.param_groups[0]["lr"]
        print(
            f"Epoch {epoch + 1}/{epochs} | train_loss={train_loss:.4f} train_acc={train_acc:.4f} | "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f} | lr={lr:.6f}"
        )

        if val_acc > best_acc:
            best_acc = val_acc
            best_epoch = epoch + 1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state is None:
        raise RuntimeError("Cannot save best group model")

    model.load_state_dict(best_state)
    model.eval()
    print(f"Best epoch: {best_epoch} | best_val_acc={best_acc:.4f}")

    onnx_path = "assets/captcha_group_model.onnx"
    dummy = torch.randn(1, 3, 64, 64).to(device)
    torch.onnx.export(model, (dummy,), onnx_path, input_names=["input"], output_names=["output"])

    labels_path = "assets/captcha_group_labels.json"
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(GROUPS, f, ensure_ascii=False, indent=2)

    print(f"Saved group model: {onnx_path}")
    print(f"Saved group labels: {labels_path}")


if __name__ == "__main__":
    main()

