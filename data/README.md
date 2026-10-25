# Data

The analysis uses licensed data from the Bloomberg Terminal and WRDS, which is not included, and public factor data from the Ken French Data Library. Set `DATA_DIR` to the folder that holds the inputs and adjust `INPUTS` in `src/common.py` to your file names.

| Input | Source | Content |
|---|---|---|
| Event list | Bloomberg Terminal, corporate-events calendar | The 685 AI-related calendar entries that pass the relevance check and the attribution, identifier and return-data filters (Table 3.1 of the thesis), one row per firm and date: company, Bloomberg ticker, date, region and Bloomberg event-type code (ID, SM and TL pooled as `Other`); the calendar description and the number of firms its record names; whether the tagged firm hosted the event; the I/B/E/S company name for European firms; a results date for events outside I/B/E/S coverage; and the Datastream ticker where it differs from Bloomberg's |
| S&P 500 constituents and returns | CRSP (`dsp500list_v2`, `dsf_v2`); Datastream after CRSP's last date | Point-in-time index membership, GICS sector from Compustat, daily returns and market capitalisation |
| STOXX Europe 600 constituents and returns | Datastream (`ds2constdly`, `wrds_ds2dsf`) | Point-in-time index membership, GICS sector from Compustat Global, daily returns and market values in US dollars |
| Earnings announcement dates | I/B/E/S (`act_epsus`, `act_epsint`) | Announcement dates for US and international firms |
| Annual accounting data | Compustat (`funda`), Compustat Global (`g_funda`) | Total assets, R&D expenditure, debt, sales, shares outstanding and share price |
| Daily factors | Ken French Data Library | Fama/French 5 Factors (2x3) [Daily] for the US and Fama/French European 5 Factors [Daily] for Europe |

Notebook 01 applies the index-membership and earnings filters that produce the final sample of 615 events. The fields each input must carry are those read in `src/common.py` and the notebooks.
