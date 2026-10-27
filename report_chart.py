"""Static plot of calculated momentum; no LLM-generated numbers."""
def plot_signals(signals, output):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    symbols = [row["symbol"] for row in signals]
    values = [row["momentum_score"] for row in signals]
    with plt.rc_context({"svg.fonttype": "none", "font.family": "DejaVu Sans"}):
        fig, ax = plt.subplots(figsize=(8, max(3, len(symbols) * 0.45)))
        ax.barh(symbols, values, color=["#168573" if value >= 0 else "#cb5348" for value in values])
        ax.axvline(0, color="#64748b", linewidth=0.8)
        ax.set_xlabel("Momentum score (weighted return, percentage points)")
        ax.set_title("Calculated momentum across supplied tickers")
        ax.invert_yaxis()
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(output, metadata={"Date": None})
        plt.close(fig)
