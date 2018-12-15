
# Modified version of the PyTorch MNIST example to log outputs for OverBoard

from __future__ import print_function
import argparse, sys
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms

sys.path.append('../')
from logger import Logger


class Net(nn.Module):
  def __init__(self):
    super(Net, self).__init__()
    self.conv1 = nn.Conv2d(1, 10, kernel_size=5)
    self.conv2 = nn.Conv2d(10, 20, kernel_size=5)
    self.conv2_drop = nn.Dropout2d()
    self.fc1 = nn.Linear(320, 50)
    self.fc2 = nn.Linear(50, 10)

  def forward(self, x):
    x = F.relu(F.max_pool2d(self.conv1(x), 2))
    x = F.relu(F.max_pool2d(self.conv2_drop(self.conv2(x)), 2))
    x = x.view(-1, 320)
    x = F.relu(self.fc1(x))
    x = F.dropout(x, training=self.training)
    x = self.fc2(x)
    return F.log_softmax(x, dim=1)

def train(args, model, device, train_loader, optimizer, epoch, logger):
  model.train()
  for batch_idx, (data, target) in enumerate(train_loader):
    data, target = data.to(device), target.to(device)
    optimizer.zero_grad()
    output = model(data)
    loss = F.nll_loss(output, target)
    loss.backward()
    optimizer.step()
    
    pred = output.max(1, keepdim=True)[1] # get the index of the max log-probability
    accuracy = pred.eq(target.view_as(pred)).double().mean()
    
      # log the loss and accuracy
    logger.update_average({'train.loss': loss.item(), 'train.accuracy': accuracy.item()})

    if batch_idx % args.log_interval == 0:
      # display values in console
      avg = logger.average()
      print(f"Train ep {epoch} ({batch_idx * len(data)}/{len(train_loader.dataset)}), loss: {avg['train.loss']:.3f}, acc: {avg['train.accuracy']*100:.1f}%")

def test(args, model, device, test_loader, logger):
  model.eval()
  with torch.no_grad():
    for data, target in test_loader:
      data, target = data.to(device), target.to(device)
      output = model(data)
      loss = F.nll_loss(output, target, reduction='sum')

      pred = output.max(1, keepdim=True)[1] # get the index of the max log-probability
      accuracy = pred.eq(target.view_as(pred)).double().mean()

      # log the loss and accuracy
      logger.update_average({'val.loss': loss.item(), 'val.accuracy': accuracy.item()})

  # display final values in console
  avg = logger.average()
  print(f"Val loss: {avg['val.loss']:.3f}, acc: {avg['val.accuracy']*100:.1f}%")

def main():
  # Training settings
  parser = argparse.ArgumentParser()
  parser.add_argument("experiment", nargs='?', default="")
  parser.add_argument('--batch-size', type=int, default=64, metavar='N',
            help='input batch size for training (default: 64)')
  parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
            help='input batch size for testing (default: 1000)')
  parser.add_argument('--epochs', type=int, default=10, metavar='N',
            help='number of epochs to train (default: 10)')
  parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
            help='learning rate (default: 0.01)')
  parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
            help='SGD momentum (default: 0.5)')
  parser.add_argument('--no-cuda', action='store_true', default=False,
            help='disables CUDA training')
  parser.add_argument('--seed', type=int, default=1, metavar='S',
            help='random seed (default: 1)')
  parser.add_argument('--log-interval', type=int, default=10, metavar='N',
            help='how many batches to wait before logging training status')
  parser.add_argument('--datadir', type=str, default='/data/joao/mnist/',
            help='MNIST data directory')
  parser.add_argument('--outputdir', type=str, default='/data/joao/mnist-pytorch/',
            help='output directory')
  args = parser.parse_args()
  use_cuda = not args.no_cuda and torch.cuda.is_available()
  args.outputdir += '/' + args.experiment

  torch.manual_seed(args.seed)

  device = torch.device("cuda" if use_cuda else "cpu")

  kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}
  train_loader = torch.utils.data.DataLoader(
    datasets.MNIST(args.datadir, train=True, download=True,
             transform=transforms.Compose([
               transforms.ToTensor(),
               transforms.Normalize((0.1307,), (0.3081,))
             ])),
    batch_size=args.batch_size, shuffle=True, **kwargs)
  test_loader = torch.utils.data.DataLoader(
    datasets.MNIST(args.datadir, train=False, transform=transforms.Compose([
               transforms.ToTensor(),
               transforms.Normalize((0.1307,), (0.3081,))
             ])),
    batch_size=args.test_batch_size, shuffle=True, **kwargs)


  model = Net().to(device)
  optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)

  stat_names = [phase + '.' + stat for stat in ('loss', 'accuracy') for phase in ('train', 'val')]

  with Logger(args.outputdir, stat_names, args) as logger:
    for epoch in range(1, args.epochs + 1):
      train(args, model, device, train_loader, optimizer, epoch, logger)
      test(args, model, device, test_loader, logger)
      logger.append()


if __name__ == '__main__':
  main()

