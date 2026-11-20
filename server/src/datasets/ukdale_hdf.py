import json
import math
import sys

import numpy as np
import tables

filename, building, meter, start, stop = sys.argv[1:]
start = np.int64(int(start) * 1_000_000_000)
stop = np.int64(int(stop) * 1_000_000_000)

with tables.open_file(filename, mode="r") as source:
    table = source.get_node(f"/building{building}/elec/meter{meter}/table")
    rows = table.read_where("(index >= start) & (index < stop)", condvars={"start": start, "stop": stop})
    kinds = table.attrs.values_block_0_kind
    names = {
        ("power", "active"): "p",
        ("power", "apparent"): "s",
        ("power", "reactive"): "q",
        ("voltage", ""): "v_rms",
        ("current", ""): "i_rms",
    }
    measures = [names.get(tuple(kind), f"ch{i + 1}") for i, kind in enumerate(kinds)]
    columns = [
        [float(value) if math.isfinite(value) else None for value in rows["values_block_0"][:, i]]
        for i in range(len(measures))
    ]
    json.dump({
        "times": (rows["index"].astype(np.float64) / 1_000_000_000).tolist(),
        "measures": measures,
        "columns": columns,
    }, sys.stdout, allow_nan=False)
