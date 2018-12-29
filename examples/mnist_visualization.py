
import math
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import ImageGrid

def vis(name, images, targets, predictions):
  fig = plt.figure(name, clear=True)

  # create a square grid big enough to hold all images, to a maximum of 5x5
  num_images = min(5**2, images.shape[0])
  rows = math.ceil(math.sqrt(num_images))
  cols = num_images // rows + 1
  grid = ImageGrid(fig, 111, nrows_ncols=(rows, cols))
  
  # show each image in turn
  images = images.numpy()
  for i in range(num_images):
    grid[i].imshow(images[i,0,:,:])

  # note: no need for plt.show
  return [fig]
