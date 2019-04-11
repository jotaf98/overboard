
import numpy as np
import matplotlib.pyplot as plt

figures = {}

def show_prediction(name, image, target, prediction):
  # convert pytorch to numpy arrays.
  # the predictions are in the log domain (F.log_softmax) so exponentiate them.
  image = image.numpy()
  prediction = prediction.exp().numpy()
  
  # get colors for bar chart
  bar_colors = get_bar_colors(prediction, target)
  
  if name not in figures:
    # create a figure from scratch (slow)
    (figure, axes) = plt.subplots(1, 2, gridspec_kw={'wspace': 0.4})
  
    # show image
    image_obj = axes[0].imshow(image, cmap='gray')

    # show predictions as a bar chart
    num_classes = len(bar_colors)
    bar_obj = axes[1].bar(np.arange(num_classes), prediction, align='center', color=bar_colors)
    
    # make axes look nicer
    configure_axes(axes, num_classes)

    # save object handles for later
    figures[name] = (figure, image_obj, bar_obj)

  else:
    # update an existing plot (fast)
    (figure, image_obj, bar_obj) = figures[name]
    image_obj.set_array(image)
    for i in range(len(bar_obj)):
      bar_obj[i].set_height(prediction[i])
      bar_obj[i].set_color(bar_colors[i])

  # return a list of figures (no need to call plt.show)
  return [figure]


def get_bar_colors(prediction, target):
  # we will show a bar chart with predictions (higher = higher confidence).
  # here we decide their colors. if the right class is guessed, it will be
  # green; otherwise it will be red, and the ground-truth black.
  bar_colors = ['white'] * prediction.shape[0]
  pred_index = np.argmax(prediction)
  
  if pred_index == target:
    bar_colors[pred_index] = 'green'
  else:
    bar_colors[pred_index] = 'red'
    bar_colors[target] = 'black'

  return bar_colors


def configure_axes(axes, num_classes):
  axes[0].set_title('Input')
  axes[0].axis('off')
  axes[1].set_title('Probabilities')
  axes[1].set_ylim([0, 1])
  axes[1].set_aspect(num_classes)
