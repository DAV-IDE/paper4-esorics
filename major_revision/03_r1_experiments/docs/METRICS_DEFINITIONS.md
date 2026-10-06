# R1 — Definizioni metodologiche (STEP 2, 5, 6)

Implementazione unica: `major_revision/mr/eal_core.py` (+ `runner.py`). Ogni scelta è un parametro esplicito; le pipeline legacy sono riprodotte per confronto (`repro_check.py`).

## 1. Serie, finestre e mapping finestra→tempo
- Serie campionata `x_i` ai tempi `t_i` (sintetico: Δt = 1 campione; proxy: 1 s; reale-A: 60 s; reale-C: 1 s).
- Finestra k: campioni `[e_k − W + 1, e_k]`, con `e_k = W − 1 + k·s`.
- **Tempo decisionale (R1) = bordo finale `t_end,k = t[e_k]`**: è causale, perché la decisione usa solo campioni già osservati.
- Legacy sintetico (upstream `export_run_results.py`): `t_center = t[e_k − W + 1 + ⌊W/2⌋]`. Non è causale, perché anticipa di circa W/2 campioni. Lo usiamo solo per riprodurre la Tab. 4.
- Legacy proxy/reale (`eal_factorial.py`): finestra trailing e H ripetuto in avanti (forward-fill) su ogni secondo. Fire e FPR sono contati in secondi, non in finestre.

## 2. Evento e intervallo d'attacco
| Dataset | t_event | t_attack_end (incluso) | Note |
|---|---|---|---|
| Sintetico drift | 1000 | 2000 | rampa 0→2.5; dopo 2000 il livello resta 2.5 (fase post) |
| Sintetico shock | 1450 | 1550 | centro 1500 ± 2σ, σ = 25 (upstream) |
| Proxy | 10500 s | 14399 s | label DDoS fino a fine serie (coda Poisson(7)): **nessuna fase post** |
| Reale A (minuto) | 1560 s (min 26) | 2760 s (min 46) | 18:56–19:16 UTC = 15:56–16:16 ADT |
| Reale C (secondo) | da schedule CIC 15:56:00 ADT | 16:16:59 ADT | BLOCKED (PCAP non disponibile) |

- **Label di finestra** = 1 se la finestra si sovrappone a `[t_event, t_attack_end]`.
- **Fasi dei fire**: *pre* = finestra interamente prima di t_event; *attack* = si sovrappone all'intervallo d'attacco; *post* = inizia dopo t_attack_end. I fire sono contati solo per `t_end ≥ t_eval_start` (fine del warm-up).

## 3. Detection e delay
- `detected` = almeno un fire su una finestra *attack*.
- `t_detect` = minimo `t_end` tra i fire su finestre attack.
- **`delay = t_detect − t_event`** (≥ 0 per costruzione), espresso nell'unità del dataset.
- Legacy (riportato a parte): primo fire-secondo ≥ primo secondo d'attacco, **anche dopo la fine dell'attacco**.

## 4. Falsi positivi
- `FPA_rate_pre` = fire pre / finestre pre (tasso per finestra).
- `FPR_window` = (fire pre + post) / finestre negative.
- `FP_per_hour` = (fire pre + post) / ore di tempo benigno valutato. Per il sintetico si usa `FP_per_1000_samples`.
- `FPR_persample` (legacy-compatibile) = secondi benigni con fire attivo (zero-order hold) / secondi benigni.
- Il FP out-of-sample per il sintetico si misura su una serie stabile indipendente (`stable_holdout`), oltre che sui segmenti pre-evento.

## 5. AUC e mapping score→tempo
- **Window-level**: score = statistica di gating della finestra; label = sovrapposizione all'attacco; solo finestre con `t_end ≥ t_eval_start`.
- **Per-sample**: lo score di ogni campione è quello dell'ultima finestra conclusa (zero-order hold causale); label = label del campione.
- Gli score sono arrotondati a 1e-12 prima del ranking: senza questo accorgimento l'AUC dipende dall'ordine di somma in floating point, perché PE e Shannon assumono pochi valori distinti (vedi finding F-03).

## 6. Varianti di gating (confronto su input identici)
| Variante | Statistica | Soglia |
|---|---|---|
| `U_raw` (codice attuale) | H_t | μ + 3σ su H in calibrazione |
| `S_norm` (Eq. 1–2 letterali) | ΔH_t = (H_t − H_base)/max(ε, H_base) | μ + 3σ su ΔH in calibrazione |
| `B_norm` (Sec. 4.4 / Q1, primaria R1) | \|ΔH_t\| | μ + 3σ su \|ΔH\| in calibrazione |
| `B_fixed015` | \|ΔH_t\| | 0.15 (iperparametro di [7]) |
| `legacy_diff` (upstream sintetico) | \|H_k − H_{k−1}\| | μ + 3σ in calibrazione |

H_base = media di H sulle finestre di calibrazione. Poiché H_base > 0, S_norm è una trasformazione affine di U_raw: **S_norm ≡ U_raw**. È verificato su tutte le celle e su tutti i seed (vedi `gating_comparison.csv`).

## 7. Regole di soglia (STEP 3)
`mu_sigma` = μ + 3σ; `q997` = quantile empirico 99,7%; `mad` = mediana + 3 × 1,4826 × MAD. Con meno di 5 valori di calibrazione finiti: τ = ∞, con warning registrato e mai scartato.

## 8. Calibrazione
- Sintetico: tutte le finestre dello scenario Stable, come nell'upstream.
- Proxy: finestre con `t_end < 600 s`.
- Reale A: `pr3_warmup600` (legacy), `preattack_causal` (`t_end < t_event`) oppure `post_retrospective_NONCAUSAL`, solo diagnostica.

## 9. Binning Shannon (STEP 6)
- `per_window`: 16 bin sul range [min, max] della finestra (codice attuale proxy).
- `global_stable`: 16 bin sul range dei campioni grezzi di calibrazione, con i valori fuori range assegnati ai bin estremi (overflow/clipping; la frazione clippata è registrata).
- `fd`: larghezza di Freedman–Diaconis sui campioni di calibrazione, con lo stesso clipping.
- `legacy_global`: range su tutti gli scenari, attacchi inclusi (upstream: leakage). Usato solo per la riproduzione.

## 10. SampEn
Template come nei codici legacy. Gestione dei casi degeneri: `nan` in R1 (escluso dalla calibrazione e contato in `nan_frac_H`); `zero` nel repo proxy; `upstream` (continuity correction 1 se A = 0).
