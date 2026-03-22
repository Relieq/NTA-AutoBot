import os
import random
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from PIL import Image


class BaseCaptchaDataset(Dataset):
    """Load toàn bộ ảnh trong dataset (không dừng ở 1 ảnh/class)."""

    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.classes = sorted([d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d))])
        self.class_to_idx = {cls_name: i for i, cls_name in enumerate(self.classes)}

        self.samples = []
        for cls_name in self.classes:
            cls_dir = os.path.join(root_dir, cls_name)
            for img_name in sorted(os.listdir(cls_dir)):
                if img_name.lower().endswith((".png", ".jpg", ".jpeg")):
                    img_path = os.path.join(cls_dir, img_name)
                    self.samples.append((img_path, self.class_to_idx[cls_name]))

        if not self.samples:
            raise RuntimeError(f"Dataset rỗng: {root_dir}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = Image.open(img_path).convert("RGB")
        return img, label


class AugmentedCaptchaDataset(Dataset):
    """Sinh dữ liệu ảo từ base samples để bù số lượng ảnh gốc ít."""

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


def set_seed(seed=42):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def evaluate(model, dataloader, criterion, device):
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for inputs, labels in dataloader:
            inputs, labels = inputs.to(device), labels.to(device)
            outputs = model(inputs)
            loss = criterion(outputs, labels)

            running_loss += loss.item() * inputs.size(0)
            preds = torch.argmax(outputs, dim=1)
            correct += int((preds == labels).sum().item())
            total += int(labels.size(0))

    loss = running_loss / max(total, 1)
    acc = correct / max(total, 1)
    return loss, acc


# ==========================================
# 2. CẤU HÌNH & TRAIN
# ==========================================
def main():
    set_seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Đang dùng device: {device}")

    train_transforms = transforms.Compose([
        transforms.Resize((64, 64)),
        # Giảm augment mạnh: chỉ xoay/góc nhỏ + thay đổi sáng nhẹ để bám sát captcha thực tế.
        transforms.RandomRotation(18),
        # Captcha thực tế có thể đảo trái-phải, nên thêm flip ngang để model học bất biến hướng.
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomAffine(degrees=0, translate=(0.06, 0.06), scale=(0.92, 1.08)),
        transforms.ColorJitter(brightness=0.12, contrast=0.12, saturation=0.06, hue=0.02),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    val_transforms = transforms.Compose([
        transforms.Resize((64, 64)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    base_dataset = BaseCaptchaDataset(root_dir="dataset")
    num_classes = len(base_dataset.classes)

    train_epoch_size = max(5000, len(base_dataset) * 120)
    val_epoch_size = max(1200, len(base_dataset) * 30)

    train_dataset = AugmentedCaptchaDataset(
        base_dataset=base_dataset,
        transform=train_transforms,
        epoch_size=train_epoch_size,
        random_sample=True,
    )
    val_dataset = AugmentedCaptchaDataset(
        base_dataset=base_dataset,
        transform=val_transforms,
        epoch_size=val_epoch_size,
        random_sample=False,
    )

    pin_memory = torch.cuda.is_available()
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True, num_workers=0, pin_memory=pin_memory)
    val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False, num_workers=0, pin_memory=pin_memory)

    # In ra danh sách class để copy vào file cấu hình
    print("Danh sách class:", base_dataset.classes)
    print(f"Số ảnh gốc: {len(base_dataset)}")
    print(f"Train epoch size: {len(train_dataset)} | Val epoch size: {len(val_dataset)}")

    # Khởi tạo model MobileNetV2 siêu nhẹ
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
    # Thay đổi lớp cuối cùng cho phù hợp số class (37)
    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

    epochs = 15
    best_val_acc = -1.0
    best_state = None
    best_epoch = -1

    print("--- BẮT ĐẦU TRAIN ---")
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        running_correct = 0
        running_total = 0

        for inputs, labels in train_loader:
            inputs, labels = inputs.to(device), labels.to(device)

            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * inputs.size(0)
            preds = torch.argmax(outputs, dim=1)
            running_correct += int((preds == labels).sum().item())
            running_total += int(labels.size(0))

        train_loss = running_loss / max(running_total, 1)
        train_acc = running_correct / max(running_total, 1)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        scheduler.step(val_acc)

        current_lr = optimizer.param_groups[0]["lr"]
        print(
            f"Epoch {epoch + 1}/{epochs} | "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} | "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.4f} | lr={current_lr:.6f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best_epoch = epoch + 1

    if best_state is None:
        raise RuntimeError("Không lưu được checkpoint tốt nhất.")

    model.load_state_dict(best_state)
    print(f"Best epoch: {best_epoch} | best_val_acc={best_val_acc:.4f}")

    # ==========================================
    # 3. EXPORT RA ONNX
    # ==========================================
    print("Đang export model ra ONNX...")
    model.eval()
    dummy_input = torch.randn(1, 3, 64, 64).to(device)
    onnx_path = "assets/captcha_model.onnx"
    torch.onnx.export(model, (dummy_input,), onnx_path,
                      input_names=['input'], output_names=['output'])
    labels_path = "assets/captcha_labels.json"
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(base_dataset.classes, f, ensure_ascii=False, indent=2)

    print(f"HOÀN TẤT! Đã lưu model tại: {onnx_path}")
    print(f"Đã lưu labels tại: {labels_path}")


if __name__ == "__main__":
    main()
