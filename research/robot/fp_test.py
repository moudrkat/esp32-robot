import sys
from research.oled import eval as E
import research.robot.talk_test as T
def fp(ckpt, device):
    m, cfg = E.load(ckpt, device)
    return m.to(device).eval(), cfg
T.load_int4 = fp
sys.exit(T.main())
