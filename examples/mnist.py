
"""
Modified version of the PyTorch MNIST example to log outputs for OverBoard
"""

from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms

from overboard_logger import Logger

try:
  import matplotlib.pyplot as plt
except ModuleNotFoundError:
  print('MatPlotLib not found.')
  plt = None


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


def confusion_matrix(name, predictions, labels):
  """Show the confusion matrix as a MatPlotLib figure.
  Note this is only executed by the OverBoard GUI, not by the training code."""
  
  num_labels = labels.max() + 1

  # create a confusion matrix
  matrix = torch.zeros((num_labels, num_labels))
  for (i, j) in zip(labels.tolist(), predictions.tolist()):
    matrix[i, j] += 1
  matrix = matrix.numpy()

  # create a figure, and show the matrix
  (figure, ax) = plt.subplots()
  ax.imshow(matrix)

  # add axis labels and tick marks
  plt.xlabel('Predictions')
  plt.ylabel('Ground-truth labels')
  plt.xticks(list(range(num_labels)), fontsize=8)
  plt.yticks(list(range(num_labels)), fontsize=8)
  figure.subplots_adjust(bottom=0.15)  # make space for bottom label

  # add a text annotation to each matrix cell
  for i in range(num_labels):
    for j in range(num_labels):
      ax.text(j, i, int(matrix[i, j]), ha="center", va="center", color="w", fontsize=8)

  # important: return the figure (or a list of figures) instead of showing it
  return figure


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
    logger.print(prefix='train')

    if logger.rate_limit(seconds=10):
      # show the images once in a while
      logger.tensor('Images', data, grayscale=True)

      # also show conv1's filters
      parameters = dict(model.named_parameters())
      logger.tensor('Conv1 filters', parameters['conv1.weight'])

      # show a confusion matrix (custom MatPlotLib plot)
      logger.visualize(confusion_matrix, 'Confusion matrix (batch)', pred.detach(), target)

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
  logger.print(prefix='val')

def main():
  # Training settings
  parser = argparse.ArgumentParser()
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
  parser.add_argument('--device', type=str, default='cuda',
            help='Device (cuda:0 for the first GPU, cuda:1 for the next, etc, or cpu)')
  parser.add_argument('--seed', type=int, default=1, metavar='S',
            help='random seed (default: 1)')
  parser.add_argument('--datadir', type=str, default='/data/mnist/',
            help='MNIST data directory')
  parser.add_argument('--outputdir', type=str, default='/data/mnist-experiments/',
            help='output directory')
  args = parser.parse_args()

  device = args.device
  if not torch.cuda.is_available():
    device = 'cpu'

  torch.manual_seed(args.seed)

  kwargs = {'num_workers': 1, 'pin_memory': True} if device != 'cpu' else {}
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

  # open logging stream
  with Logger(args.outputdir, meta=args) as logger:
    # do training
    for epoch in range(1, args.epochs + 1):
      train(args, model, device, train_loader, optimizer, epoch, logger)
      test(args, model, device, test_loader, logger)

      # record average statistics collected over this epoch (with logger.update_average)
      logger.append()


if __name__ == '__main__':
  main()

