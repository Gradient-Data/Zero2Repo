# feature: F03
"""Small public-interface network builders for electrical acceptance checks."""

import pandas as pd
from velmora import Network


def electrical_pair():
    n = Network()
    n.add('Carrier', 'AC')
    n.add('Bus', ['west', 'east'], v_nom=110)
    n.add('Line', 'circuit', bus0='west', bus1='east', r=0.2, x=0.4,
          s_nom=100)
    return n


def seasonal_pair():
    n = electrical_pair()
    n.set_snapshots(pd.to_datetime(['2025-03-31', '2025-04-01',
                                    '2025-09-30', '2025-10-01']))
    return n
