
# Example: Log synthetic data

import sys, math, random, time

from overboard import Logger

print("Open OverBoard in another terminal: python3 -m overboard ./logs")
print("Then press Enter here to start logging.")
input()

# pretend that there are 10 runs/experiments
for run in range(10):
  # set output directory
  directory = 'logs/sinusoid' + str(run)

  # select arguments specific to this run (could have used the argparse module to get from command-line)
  # here we just select the arguments of a sinusoid
  (phase, amp) = (random.random() * 2 * math.pi, random.random())
  args = {'phase': phase, 'amplitude': amp}
  print("Starting run", run, args)

  # open file for logging
  with Logger(directory, meta=args) as logger:
    # simulate a few iterations
    for iteration in range(100):
      # obtain output values
      angle = iteration / 100 * (2 * math.pi)
      (cos, sin) = (amp * math.cos(angle + phase), amp * math.sin(angle + phase))
      outputs = {'sine': sin, 'cosine': cos}

      # log them
      logger.append(outputs)
      logger.print(outputs)  # also display in terminal

      # wait a bit
      time.sleep(0.1)
