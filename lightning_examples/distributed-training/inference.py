import torch
import torch.nn.functional as F
from pytorch_lightning import LightningDataModule, LightningModule, seed_everything, Trainer
from torch.utils.data import DataLoader, Dataset, random_split
from torchmetrics import Accuracy
from torchvision import transforms
from torchvision.datasets import MNIST


class MNISTDataModule(LightningDataModule):

    def __init__(self, data_dir: str = "./", batch_size: int = 16):
        super().__init__()
        self.data_dir = data_dir
        self.batch_size = batch_size
        self.transform = transforms.Compose([
            transforms.ToTensor(), transforms.Normalize((0.1307, ), (0.3081, ))
        ])
        self.dims = (1, 28, 28)
        self.num_classes = 10

    def prepare_data(self):
        # only downloads the data once
        MNIST(self.data_dir, train=True, download=True)
        MNIST(self.data_dir, train=False, download=True)

    def setup(self, stage=None):
        if stage == 'fit' or stage is None:
            mnist_full = MNIST(self.data_dir, train=True, transform=self.transform)
            self.mnist_train, self.mnist_val = random_split(mnist_full, [55000, 5000])
        if stage == 'test' or stage is None:
            self.mnist_test = MNIST(self.data_dir, train=False, transform=self.transform)

    def train_dataloader(self):
        return DataLoader(self.mnist_train, batch_size=self.batch_size)

    def val_dataloader(self):
        return DataLoader(self.mnist_val, batch_size=self.batch_size)

    def test_dataloader(self):
        return DataLoader(self.mnist_test, batch_size=self.batch_size)


class TutorialModule(LightningModule):

    def __init__(
        self,
        hidden_dim: int = 128,
        learning_rate: float = 0.0001,
    ):
        super().__init__()
        self.save_hyperparameters()
        self.l1 = torch.nn.Linear(28 * 28, self.hparams.hidden_dim)
        self.l2 = torch.nn.Linear(self.hparams.hidden_dim, 10)
        self.val_accuracy = Accuracy(num_classes=10)
        self.test_accuracy = Accuracy(num_classes=10)

    def forward(self, x):
        x = x.view(x.size(0), -1)
        x = torch.relu(self.l1(x))
        x = self.l2(x)
        return x

    def training_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = F.cross_entropy(y_hat, y)
        return {"loss": loss, "y_hat": y_hat.detach()}

    def validation_step(self, batch, batch_idx):
        x, y = batch
        prob = F.softmax(self(x), dim=1)
        pred = torch.argmax(prob, dim=1)
        self.log("val_acc", self.val_accuracy(pred, y), prog_bar=True)

    def test_step(self, batch, batch_idx):
        x, y = batch
        prob = F.softmax(self(x), dim=1)
        pred = torch.argmax(prob, dim=1)
        self.log("test_acc", self.test_accuracy(pred, y))

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=self.hparams.learning_rate)


class DDPInferenceModel(TutorialModule):

    def predict_step(self, batch, batch_idx):
        x, y = batch
        prob = F.softmax(self(x), dim=1)
        pred = torch.argmax(prob, dim=1)
        return pred


def run_train():
    model = TutorialModule()
    trainer = Trainer(
        gpus=2,
        accelerator="ddp",
        max_epochs=1,
    )
    trainer.fit(model)
    best_path = trainer.checkpoint_callback.best_model_path
    print(f"Best model: {best_path}")
    return best_path


def run_predict(best_path):
    model = DDPInferenceModel()
    datamodule = MNISTDataModule()
    trainer = Trainer(
        gpus=2,
        accelerator="ddp",
        limit_predict_batches=4,
    )
    predictions = trainer.predict(
        model, dataloaders=datamodule.test_dataloader(), ckpt_path=best_path, return_predictions=True
    )
    print(predictions)


if __name__ == "__main__":
    best_path = run_train()
    run_predict(best_path)