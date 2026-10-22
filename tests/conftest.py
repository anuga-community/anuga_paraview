import glob
import os

import pytest

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
FILES = sorted(glob.glob(os.path.join(DATA, '*.sww')))

# A file without momentum (no speed) and one with momentum, centroid
# values and an elevation that changes over time.
NO_MOMENTUM = os.path.join(DATA, 'cairns.sww')
DAM_BREAK = os.path.join(DATA, 'output_run_dam_break_change_elevation.sww')


@pytest.fixture(params=FILES, ids=os.path.basename)
def sww_path(request):
    return request.param
