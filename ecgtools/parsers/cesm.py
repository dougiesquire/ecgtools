import dataclasses
import pathlib

import cf_xarray  # noqa
import xarray as xr

from .utilities import extract_attr_with_regex

_STREAMS_DICT = {
    'cam.h0': {'component': 'atm', 'frequency': 'month_1'},
    'cam.h1': {'component': 'atm', 'frequency': 'day_1'},
    'cam.h2': {'component': 'atm', 'frequency': 'hour_6'},
    'cam.h3': {'component': 'atm', 'frequency': 'hour_3'},
    'cam.h4': {'component': 'atm', 'frequency': 'hour_1'},
    'cam.h5': {'component': 'atm', 'frequency': 'subhour_3'},
    'cam.h6': {'component': 'atm', 'frequency': 'day_1'},
    'cam.h7': {'component': 'atm', 'frequency': 'day_5'},
    'cam.h8': {'component': 'atm', 'frequency': 'day_10'},
    'clm2.h0': {'component': 'lnd', 'frequency': 'month_1'},
    'clm.h1': {'component': 'lnd', 'frequency': 'month_1'},
    'clm.h2': {'component': 'lnd', 'frequency': 'month_1'},
    'clm.h3': {'component': 'lnd', 'frequency': 'day_365'},
    'clm.h4': {'component': 'lnd', 'frequency': 'day_365'},
    'clm.h5': {'component': 'lnd', 'frequency': 'day_1'},
    'clm.h6': {'component': 'lnd', 'frequency': 'day_1'},
    'clm.h7': {'component': 'lnd', 'frequency': 'hour_3'},
    'clm.h8': {'component': 'lnd', 'frequency': 'day_1'},
    'mosart.h0': {'component': 'rof', 'frequency': 'month_1'},
    'mosart.h1': {'component': 'rof', 'frequency': 'day_1'},
    'mosart.h2': {'component': 'rof', 'frequency': 'hour_6'},
    'mosart.h3': {'component': 'rof', 'frequency': 'hour_3'},
    'pop.h': {'component': 'ocn', 'frequency': 'month_1'},
    'pop.h.nday1': {'component': 'ocn', 'frequency': 'day_1'},
    'pop.h.nyear1': {'component': 'ocn', 'frequency': 'year_1'},
    'pop.h.ecosys': {'component': 'ocn', 'frequency': 'month_1'},
    'pop.h.ecosys.nday1': {'component': 'ocn', 'frequency': 'day_1'},
    'pop.h.ecosys.nyear1': {'component': 'ocn', 'frequency': 'year_1'},
    'cice.h': {'component': 'ice', 'frequency': 'month_1'},
    'cice.h1': {'component': 'ice', 'frequency': 'day_1'},
    'cism.h': {'component': 'glc', 'frequency': 'year_1'},
    'cism.h1': {'component': 'glc', 'frequency': 'month_1'},
    'ww3.h': {'component': 'wav', 'frequency': 'month_1'},
}


@dataclasses.dataclass
class Stream:
    name: str
    component: str
    frequency: str


# Make sure to sort the streams in reverse, the reverse=True is required so as
# not to confuse `pop.h.ecosys.nday1` and `pop.h.ecosys.nday1` when looping over
# the list of streams in the parsing function

CESM_STREAMS = [
    Stream(name=key, component=value['component'], frequency=value['frequency'])
    for key, value in sorted(_STREAMS_DICT.items(), reverse=True)
]


def parse_date(date):
    def _join(a):
        return ''.join(a)

    data = list(str(date))
    if len(data) == 10:
        return f'{_join(data[:4])}-{_join(data[4:6])}-{_join(data[6:8])}T{_join(data[8:])}'
    elif len(data) == 8:
        return f'{_join(data[:4])}-{_join(data[4:6])}-{_join(data[6:])}'
    elif len(data) == 6:
        return f'{_join(data[:4])}-{_join(data[4:])}'
    elif len(data) == 4:
        return str(date)
    return date


def parse_cesm_history(file):
    file = pathlib.Path(file)
    info = {}
    try:
        for stream in CESM_STREAMS:
            extracted_stream = extract_attr_with_regex(file.stem.lower(), stream.name.lower())
            if extracted_stream:
                info['component'] = stream.component
                info['stream'] = stream.name
                z = file.stem.lower().split(extracted_stream)
                info['case'] = z[0].strip('.')
                info['frequency'] = stream.frequency
                info['date'] = z[-1].strip('.')
                break
        with xr.open_dataset(file, chunks={}, decode_times=False) as ds:
            time = ds.cf['T'].name
            try:
                time_bounds = ds.cf.get_bounds('time').name
            except KeyError:
                time_bounds = ''
            variables = [
                v
                for v, da in ds.variables.items()
                if time in da.dims and v not in {time, time_bounds}
            ]
            info['variables'] = variables
            info['path'] = str(file)
        return info

    except Exception:
        return {}


def parse_smyle(file):
    """Parser for CESM2 Seasonal-to-Multiyear Large Ensemble (SMYLE)"""
    try:
        with xr.open_dataset(file, chunks={}, decode_times=False) as ds:
            file = pathlib.Path(file)
            parts = file.parts
            # Case
            case = parts[-6]
            # Extract the component from the file string
            component = parts[-5]

            # Extract the frequency
            frequency = parts[-2]

            date_regex = r'\d{10}-\d{10}|\d{8}-\d{8}|\d{6}-\d{6}|\d{4}-\d{4}'
            date_range = extract_attr_with_regex(parts[-1], date_regex)
            # Pull out the start and end time
            start_time, end_time = date_range.split('-')

            # Extract variable and stream
            y = parts[-1].split(date_range)[0].strip('.').split('.')
            variable = y[-1]
            stream = '.'.join(y[-3:-1])

            # Extract init_year, init_month, member_id
            z = extract_attr_with_regex(case, r'\d{4}-\d{2}.\d{3}').split('.')
            inits = z[0].split('-')
            init_year = int(inits[0])
            init_month = int(inits[1])
            member_id = int(z[-1])
            x = case.split(z[0])[0].strip('.').split('.')
            experiment = x[-2]
            grid = x[-1]

            # Get the long name from dataset
            long_name = ds[variable].attrs.get('long_name')

            # Grab the units of the variable
            units = ds[variable].attrs.get('units')

            # Set the default of # of vertical levels to 1
            vertical_levels = 1

            try:
                vertical_levels = ds[ds.cf['vertical'].name].size
            except (KeyError, AttributeError, ValueError):
                pass

            # Use standard region names
            regions = {
                'atm': 'global',
                'ocn': 'global_ocean',
                'lnd': 'global_land',
                'ice': 'global',
            }

            spatial_domain = regions.get(component, 'global')

        return {
            'component': component,
            'case': case,
            'experiment': experiment,
            'variable': variable,
            'long_name': long_name.lower(),
            'frequency': frequency,
            'stream': stream,
            'member_id': member_id,
            'init_year': init_year,
            'init_month': init_month,
            'vertical_levels': vertical_levels,
            'units': units,
            'spatial_domain': spatial_domain,
            'grid': grid,
            'start_time': parse_date(start_time),
            'end_time': parse_date(end_time),
            'path': str(file),
        }

    except Exception:
        return {}
