#!/usr/bin/env python3
import os
import sys
import time
import signal
import traceback
import usb1
from panda import Panda, PandaDFU
from multiprocessing import Pool

jungle = "JUNGLE" in os.environ
if jungle:
  from panda_jungle import PandaJungle  # pylint: disable=import-error

import cereal.messaging as messaging
from selfdrive.boardd.boardd import can_capnp_to_can_list

def initializer():
  """Ignore CTRL+C in the worker process.
  source: https://stackoverflow.com/a/44869451 """
  signal.signal(signal.SIGINT, signal.SIG_IGN)

def send_thread(sender_serial):
  while True:
    try:
      if jungle:
        sender = PandaJungle(sender_serial)
      else:
        sender = Panda(sender_serial)
        sender.set_safety_mode(Panda.SAFETY_ALLOUTPUT)

      sender.set_can_loopback(False)
      can_sock = messaging.sub_sock('can')

      while True:
        tsc = messaging.recv_one(can_sock)
        snd = can_capnp_to_can_list(tsc.can)
        snd = list(filter(lambda x: x[-1] <= 2, snd))

        try:
          sender.can_send_many(snd)
        except usb1.USBErrorTimeout:
          pass

        # Drain panda message buffer
        sender.can_recv()
    except Exception:
      traceback.print_exc()
      time.sleep(1)

if __name__ == "__main__":
  if jungle:
    serials = PandaJungle.list()
  else:
    serials = Panda.list()
  num_senders = len(serials)

  if num_senders == 0:
    print("No senders found. Exiting")
    sys.exit(1)
  else:
    print("%d senders found. Starting broadcast" % num_senders)

  if "FLASH" in os.environ:
    for s in PandaDFU.list():
      PandaDFU(s).recover()

    time.sleep(1)
    for s in serials:
      Panda(s).recover()
      Panda(s).flash()

  pool = Pool(num_senders, initializer=initializer)
  pool.map_async(send_thread, serials)

  while True:
    try:
      time.sleep(10)
    except KeyboardInterrupt:
      pool.terminate()
      pool.join()
      raise

