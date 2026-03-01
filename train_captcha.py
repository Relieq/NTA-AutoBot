import os
import random
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from PIL import Image


# ==========================================
# 1. CUSTOM DATASET (TĂNG CƯỜNG DỮ LIỆU)
# ==========================================
class CaptchaDataset(Dataset):
    def __init__(self, root_dir, transform=None, epoch_size=2000):
        """
        epoch_size: Số lượng ảnh ảo muốn sinh ra trong 1 epoch.
        Vì ta chỉ có 37 ảnh gốc, ta sẽ random bốc ảnh và apply transform liên tục.
        """
        self.root_dir = root_dir
        self.transform = transform
        self.epoch_size = epoch_size
        self.classes = sorted(os.listdir(root_dir))
        self.class_to_idx = {cls_name: i for i, cls_name in enumerate(self.classes)}

        # Load sẵn toàn bộ 37 ảnh gốc vào RAM cho cực nhanh
        self.images = []
        for cls_name in self.classes:
            cls_dir = os.path.join(root_dir, cls_name)
            for img_name in os.listdir(cls_dir):
                if img_name.endswith(('.png', '.jpg', '.jpeg')):
                    img_path = os.path.join(cls_dir, img_name)
                    # Convert RGBA sang RGB để tránh lỗi kênh Alpha của ảnh PNG
                    img = Image.open(img_path).convert('RGB')
                    self.images.append((img, self.class_to_idx[cls_name]))
                    break  # Chỉ lấy 1 ảnh mỗi class

    def __len__(self):
        return self.epoch_size

    def __getitem__(self, idx):
        # Bốc random 1 ảnh bất kỳ trong 37 ảnh
        img, label = random.choice(self.images)
        if self.transform:
            img = self.transform(img)
        return img, label


# ==========================================
# 2. CẤU HÌNH & TRAIN
# ==========================================
def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Đang dùng device: {device}")

    # Cấu hình biến đổi ảnh (Siêu quan trọng cho bài toán của bạn)
    data_transforms = transforms.Compose([
        transforms.Resize((64, 64)),
        transforms.RandomRotation(180),  # Xoay ngẫu nhiên từ -180 đến 180 độ
        transforms.ColorJitter(brightness=0.2, contrast=0.2),  # Đổi ánh sáng nhẹ
        transforms.RandomHorizontalFlip(),  # Lật ngang
        transforms.RandomVerticalFlip(),  # Lật dọc
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    # Khởi tạo dataset
    dataset = CaptchaDataset(root_dir="dataset", transform=data_transforms, epoch_size=3000)
    dataloader = DataLoader(dataset, batch_size=32, shuffle=True)
    num_classes = len(dataset.classes)

    # In ra danh sách class để copy vào file cấu hình
    print("Danh sách class:", dataset.classes)

    # Khởi tạo model MobileNetV2 siêu nhẹ
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
    # Thay đổi lớp cuối cùng cho phù hợp số class (37)
    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    # Train khoảng 5-10 Epoch là đủ vì bài toán khá dễ
    epochs = 10
    print("--- BẮT ĐẦU TRAIN ---")
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for inputs, labels in dataloader:
            inputs, labels = inputs.to(device), labels.to(device)

            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * inputs.size(0)

        epoch_loss = running_loss / len(dataset)
        print(f"Epoch {epoch + 1}/{epochs} - Loss: {epoch_loss:.4f}")

    # ==========================================
    # 3. EXPORT RA ONNX
    # ==========================================
    print("Đang export model ra ONNX...")
    model.eval()
    dummy_input = torch.randn(1, 3, 64, 64).to(device)
    onnx_path = "assets/captcha_model.onnx"
    torch.onnx.export(model, dummy_input, onnx_path,
                      input_names=['input'], output_names=['output'])
    print(f"HOÀN TẤT! Đã lưu model tại: {onnx_path}")


if __name__ == "__main__":
    main()
