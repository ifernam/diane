from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from collections.abc import Iterable, MutableSet, Collection
import math
from operator import itemgetter

import pandas as pd
import numpy as np
from scipy.signal import welch, find_peaks, savgol_filter, correlate, correlation_lags
from scipy.interpolate import make_interp_spline

from diane.temporal import TimeSet, TimeInterval, Duration, Timestamp
from diane.activities import Activity
from diane.sessions import Session
from diane.repository import Repository, RepositoryError, UnknownActivityError, ActivitiesNotTracked


class AssistedRepositoryError(RepositoryError):
    '''The base exception for all assisted repository errors.'''
    pass



class AssistedRepository(Repository):
    '''Smart wrapper to the 'Repository'.
    
    This provides some 'assisted' features, such as merging
    sessions that are close in time and have the same activities.
    '''


    @staticmethod
    def is_good(session: Session) -> bool:
        '''Return `True` if the given session is 'good'.
        
        Assess how 'good' the session is according to certain criteria.
        'Goodness' usually means that the pauses between activity
        intervals are not too long.

        Returns:
            `bool`: `True` if the session is 'good', `False` otherwise.
        '''

        return session.timeset.max_gap_duration <= session.timeset.min_component_duration
    

    def merge_if_good(self, *sessions: Session) -> Session:
        '''Merge the given sessions (which must already be
        in the repository) if the result will be 'good' and add
        the merged session to the repository.

        The sessions are merged only if they have **identical activity
        sets** and **the result will be 'good'**. A new session
        is created with the same activities that unites the time sets
        and messages of the original ones. The original sessions
        are removed from the repository and the merged session is added.

        Args:
            `*sessions` (`Session`): The sessions for merging.

        Returns:
            `Session`: The merged session.

        Raises:
            `KeyError`: If at least one of the given sessions
                is not in the repository.
            `ValueError`: If no sessions are provided,
                or if the sessions cannot be merged (e.g., different
                activity sets or the result won't be 'good').
        '''
        
        if not sessions:
            raise ValueError('At least one session required for merge.')
        
        missing = {s for s in sessions if s not in self}
        if len(missing) == 1:
            raise KeyError('One session is missing from the repository.')
        elif len(missing) > 1:
            raise KeyError(f'There are {len(missing)} sessions missing from the repository')

        try:
            merged = Session.merge(*sessions)
        except ValueError as e:
            raise ValueError(f'Unable to merge the sessions. {e}.') from e
        
        if not AssistedRepository.is_good(merged):
            raise ValueError(f'The sessions won\'t merge because the result won\'t be \'good\'.')
        
        for s in sessions:
            self.discard(s)
        self.add(merged)

        return merged
    

    def add_and_merge(self, session: Session) -> Session:
        '''Add the given session to the repository and repeatedly
        merge it with the closest session in time until no further merge
        is possible. The final merged session is returned.

        Args:
            `session` (`Session`): The session to add and merge.

        Returns:
            `Session`: The final merged session.
        '''

        self.add(session)
        for s in self.iter_closest_in_time_to(session):
            if TimeSet.dist(session.timeset, s.timeset) > session.timeset.min_component_duration:
                # Closest session is too far for merging.
                break

            # Try merge.
            try:
                session = self.merge_if_good(session, s)
            except ValueError:
                # Cannot merge with this session `s`. Try next.
                continue

        return session



    class Regularity:
        index: float
        period: Duration | None
        confidence: float

        def __init__(self, index: float, period: Duration | None, confidence) -> None:
            self.index = index
            self.period = period
            self.confidence = confidence



    def _activity_signal(
        self,
        *activities: Activity | str,
        timeinterval: TimeInterval
    ) -> np.ndarray:
        """Convert the tracked activities data into a binary signal.

        Args:
            *activities (Activity | str): Activities or slugs
                to be converted into a binary signal.
            timeinterval: The finite time period over which
                the activities are considered.

        Returns:
            np.ndarray: A binary signal where 1 indicates the presence
                of the specified activities and 0 indicates their
                absence. The signal is sampled at a one-minute interval.

        Raises:
            UnknownActivityError: If any given activity or slug
                is not listed in the activities registry.
            TypeError: If any argument is neither an Activity nor a str.
            ActivitiesNotTracked: The activities provided have not been
                tracked.
            ValueError: If the time interval is unbounded.
        """

        if timeinterval.is_unbounded:
            raise ValueError('The time interval is unbounded.')

        # Find the sessions that correspond to the given activities.
        sessions = self.find_by_activities(*activities)

        # If no session is found, return an empty `numpy` array.
        if not sessions:
            minutes = math.ceil(timeinterval.duration / Duration.minute())
            return np.empty(minutes, float)

        # Roughen up the data by treating each session as a single
        # interval.
        session_intervals = [s.timeset.span() for s in sessions]

        # If no time interval is specified, the entire timeline
        # is considered.
        if timeinterval is None:
            timeinterval = TimeInterval.timeline()

        # Obtain a time set of activity for convertion to a binary
        # signal by uniting the intervals, intersection with the time
        # window and blowing up points to the nearest minute.
        timeset = TimeSet.union(*session_intervals) & timeinterval
        timeset_ceil = timeset.ceil_to_minute(blow_up_points=True)

        # If an empty time set is obtained, return an empty `numpy`
        # array.
        if not timeset_ceil:
            minutes = math.ceil(timeinterval.duration / Duration.minute())
            return np.empty(minutes, float)

        # `pandas` timestamps.
        pd_intervals = pd.DataFrame(
            {
                'start': [
                    pd.to_datetime(c.start.timestamp.datetime)
                    for c in timeset_ceil.components
                ],
                'end': [
                    pd.to_datetime(c.end.timestamp.datetime)
                    for c in timeset_ceil.components
                ],
            }
        )

        full_range = pd.date_range(
            pd.to_datetime(timeinterval.start.timestamp.datetime),
            pd.to_datetime(timeinterval.end.timestamp.datetime)
                - pd.Timedelta(minutes=1),
            freq='min',
        )

        if full_range.empty:
            minutes = math.ceil(timeinterval.duration / Duration.minute())
            return np.empty(minutes, float)

        binary = pd.Series(0.0, index=full_range)
        for _, row in pd_intervals.iterrows():
            binary[row['start']: row['end'] - pd.Timedelta(minutes=1)] = 1.0

        signal = binary.values

        # Subtract the mean.
        signal = signal - signal.mean()

        return signal


    @staticmethod
    def _regularity_welch_by_signal(
            signal: np.ndarray
    ) -> Regularity:
        """
        Returns:
            Regularity(
                index: normalized regularity in [0, 1],
                period: strongest detected period, or None,
                confidence: confidence in [0, 1]
            )
        """

        fs = 1 / 60  # One sample per minute, in Hz.
        nperseg = min(signal.size, 1440 * 7)
        if nperseg < 8:
            return AssistedRepository.Regularity(0.0, None, 0.0)

        noverlap = nperseg // 2

        freqs, psd = welch(
            signal,
            fs=fs,
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
            window="hann",
            scaling="density",
        )

        # Keep only positive frequencies.
        pos_mask = freqs > 0
        freqs = freqs[pos_mask]
        psd = psd[pos_mask]

        if freqs.size == 0:
            return AssistedRepository.Regularity(0.0, None, 0.0)

        periods = 1 / (freqs * 3600)  # hours

        # Score bands.
        total_mask = (periods >= 12) & (periods <= 48)
        circ_mask = (periods >= 20) & (periods <= 30)

        # Require enough support in both bands.
        if total_mask.sum() < 2 or circ_mask.sum() < 2:
            return AssistedRepository.Regularity(0.0, None, 0.0)

        P_total = np.trapezoid(psd[total_mask], freqs[total_mask])
        P_circ = np.trapezoid(psd[circ_mask], freqs[circ_mask])

        if P_total <= 0 or P_circ <= 0:
            return AssistedRepository.Regularity(0.0, None, 0.0)

        index = float(np.clip(P_circ / P_total, 0.0, 1.0))

        # Peak detection for the strongest period.
        roi = (periods >= 12) & (periods <= 48)
        p = periods[roi]
        psd_roi = psd[roi]

        if p.size < 5:
            return AssistedRepository.Regularity(index, None, 0.0)

        win_len = min(p.size, max(5, int(p.size * 0.25)))
        if win_len % 2 == 0:
            win_len += 1

        if 5 <= win_len <= p.size:
            psd_smooth = savgol_filter(psd_roi, win_len, polyorder=3)
        else:
            psd_smooth = psd_roi

        safe_mask = (periods >= 2) & (periods <= 10)
        safe_vals = psd[safe_mask]
        if safe_vals.size >= 2:
            noise = float(np.median(safe_vals))
        elif psd_roi.size >= 2:
            noise = float(np.median(psd_roi))
        else:
            noise = 0.0

        noise = max(noise, np.finfo(float).eps)

        peaks, properties = find_peaks(psd_smooth, prominence=0.1 * noise)

        if len(peaks) == 0 or "prominences" not in properties:
            return AssistedRepository.Regularity(index, None, 0.0)

        peak_periods = p[peaks]
        prominences = properties["prominences"]

        # Prefer peaks in the circadian window, otherwise take
        # the strongest one.
        circ_peak_positions = np.flatnonzero(
            (peak_periods >= 20) & (peak_periods <= 28)
        )
        if circ_peak_positions.size > 0:
            candidate_positions = circ_peak_positions
        else:
            candidate_positions = np.arange(len(peaks))

        best_local = candidate_positions[
            np.argmax(prominences[candidate_positions])
        ]
        strongest_period_hours = float(peak_periods[best_local])

        period = Duration.finite(
            datetime.timedelta(hours=strongest_period_hours)
        )

        prom_sum = float(np.sum(prominences))
        if prom_sum > 0:
            confidence = float(
                np.clip(prominences[best_local] / prom_sum, 0.0, 1.0)
            )
        else:
            confidence = 0.0

        return AssistedRepository.Regularity(index, period, confidence)


    def regularity_welch(
        self,
        *activities: Activity | str,
        timeinterval: TimeInterval | None = None
    ) -> Regularity:
        """
        Returns:
            Regularity(
                index: normalized regularity in [0, 1],
                period: strongest detected period, or None,
                confidence: confidence in [0, 1]
            )
        """

        signal = self._activity_signal(*activities, timeinterval=timeinterval)
        return AssistedRepository._regularity_welch_by_signal(signal)


    @staticmethod
    def _regularity_acf_by_signal(
        signal: np.ndarray
    ) -> Regularity:
        """
        Autocorrelation-based regularity.

        Returns:
            Regularity(
                index: normalized regularity in [0, 1],
                period: strongest detected period, or None,
                confidence: confidence in [0, 1]
            )
        """

        if not signal.any():
            return AssistedRepository.Regularity(0.0, None, 0.0)

        # Autocorrelation.
        acf = correlate(signal, signal, mode='full', method='fft')
        lags = correlation_lags(len(signal), len(signal), mode='full')

        # Keep non-negative lags so lag 0 can be used for normalization.
        pos_mask = lags >= 0
        acf = acf[pos_mask]
        lags = lags[pos_mask]

        if acf.size == 0 or acf[0] <= 0:
            return AssistedRepository.Regularity(0.0, None, 0.0)

        # Normalize so ACF(0) = 1.
        acf = acf / acf[0]

        # Remove lag 0 for analysis.
        acf = acf[1:]
        lags = lags[1:]

        if acf.size == 0:
            return AssistedRepository.Regularity(0.0, None, 0.0)

        lag_hours = lags / 60.0

        # Same style of search ranges as Welch:
        #   total: 12–48 h
        #   circadian index band: 20–30 h
        total_mask = (lag_hours >= 12) & (lag_hours <= 48)
        circ_mask = (lag_hours >= 20) & (lag_hours <= 30)

        if total_mask.sum() < 2 or circ_mask.sum() < 2:
            return AssistedRepository.Regularity(0.0, None, 0.0)

        acf_total = np.clip(acf[total_mask], 0.0, None)
        acf_circ = np.clip(acf[circ_mask], 0.0, None)

        total_mass = float(np.sum(acf_total))
        circ_mass = float(np.sum(acf_circ))

        if total_mass <= 0 or circ_mass <= 0:
            return AssistedRepository.Regularity(0.0, None, 0.0)

        index = float(np.clip(circ_mass / total_mass, 0.0, 1.0))

        # Strongest period search in 12–48 h ROI.
        p = lag_hours[total_mask]
        acf_roi = acf[total_mask]

        if p.size < 5:
            return AssistedRepository.Regularity(index, None, 0.0)

        # Light smoothing for stable period selection.
        win_len = min(p.size, max(5, int(p.size * 0.25)))
        if win_len % 2 == 0:
            win_len += 1

        if 5 <= win_len <= p.size:
            acf_smooth = savgol_filter(acf_roi, win_len, polyorder=3)
        else:
            acf_smooth = acf_roi

        # Prefer the circadian window; otherwise use the whole ROI.
        circ_period_mask = (p >= 20) & (p <= 28)
        if circ_period_mask.any():
            candidate_values = np.clip(acf_smooth[circ_period_mask], 0.0, None)
            candidate_periods = p[circ_period_mask]
        else:
            candidate_values = np.clip(acf_smooth, 0.0, None)
            candidate_periods = p

        if candidate_values.size == 0 or candidate_values.max() <= 0:
            return AssistedRepository.Regularity(index, None, 0.0)

        best_local = int(np.argmax(candidate_values))
        strongest_period_hours = float(candidate_periods[best_local])
        period = Duration.finite(datetime.timedelta(
            hours=strongest_period_hours)
        )

        # Confidence: peak contrast against the ROI background.
        roi_positive = np.clip(acf_roi, 0.0, None)

        if roi_positive.size > 0:
            background = float(np.median(roi_positive))
        else:
            background = 0.0

        best_value = float(np.clip(candidate_values[best_local], 0.0, None))

        # Soft normalization into [0, 1].
        # If best_value is much larger than background, confidence -> 1.
        # If best_value is close to background, confidence -> ~0.5.
        confidence = float(
            np.clip(
                best_value / (best_value + background + np.finfo(float).eps),
                0.0,
                1.0,
                )
        )

        return AssistedRepository.Regularity(index, period, confidence)


    def regularity_acf(
        self,
        *activities: Activity | str,
        timeinterval: TimeInterval | None = None
    ) -> Regularity:
        """
        Autocorrelation-based regularity.

        Returns:
            Regularity(
                index: normalized regularity in [0, 1],
                period: strongest detected period, or None,
                confidence: confidence in [0, 1]
            )
        """

        signal = self._activity_signal(*activities, timeinterval=timeinterval)
        return AssistedRepository._regularity_acf_by_signal(signal)


    def _regularity_by_signal(
        self,
        signal: np.ndarray
    ) -> Regularity:
        welch_contribution = 0.7
        acf_contribution = 0.3

        regularity_welsh = self._regularity_welch_by_signal(signal)
        regularity_acf = self._regularity_acf_by_signal(signal)

        regularity_index = (
            welch_contribution
            * regularity_welsh.index * regularity_welsh.confidence
            + acf_contribution
            * regularity_acf.index * regularity_acf.confidence
        )

        regularity_confidence = (
            welch_contribution * regularity_welsh.confidence
            + acf_contribution * regularity_acf.confidence
        )

        if regularity_welsh.period and regularity_acf.period:
            regularity_period = (
                (regularity_welsh.period + regularity_acf.period) / 2.
            )
        else:
            regularity_period = (
                regularity_welsh.period or regularity_acf.period
            )

        return AssistedRepository.Regularity(
            index=regularity_index,
            confidence=regularity_confidence,
            period=regularity_period
        )


    def regularity(
        self,
        *activities: Activity | str,
        timeinterval: TimeInterval
    ) -> Regularity:
        signal = self._activity_signal(*activities, timeinterval=timeinterval)
        return self._regularity_by_signal(signal)


    def mean_regularity_index(
        self,
        *activities: Activity | str,
        timestamp: Timestamp,
        observations_range: TimeInterval
    ) -> float:
        """Calculate the mean regularity index.

        Calculates the mean regularity index over a two-week period
        centered on the given timestamp.

        Args:
            *activities: Activity | str: The given activities.
            timestamp: Timestamp: The midpoint of the period used
                to calculate the mean regularity index.
            observations_range: TimeInterval: The range of observations
                to consider.

        Returns:
            float: The mean regularity index.
        """


        half_window_duration = Duration.week()
        preliminary_window = TimeInterval.closed(
            timestamp - half_window_duration, timestamp + half_window_duration
        )
        window = preliminary_window & observations_range
        if not window:
            raise ValueError(
                'Empty time interval for mean regularity index calculation.'
            )

        regularity_index = {}
        t = window.start.timestamp
        end = window.end.timestamp
        while t <= end:
            window = TimeInterval.closed(
                t - half_window_duration, t + half_window_duration
            ) & observations_range
            regularity_index[t] = self.regularity(
                *activities, timeinterval=window
            ).index
            t += Duration.day()

        return sum(regularity_index.values()) / len(regularity_index)


    @dataclass
    class RegularityPlot:
        x: list[float] = field(default_factory=list)
        y: list[float] = field(default_factory=list)
        tick_positions: list[float] = field(default_factory=list)
        tick_labels: list[str] = field(default_factory=list)
        habit_threshold: float = 0.3



    def regularity_plot(
        self,
        *activities: Activity | str
    ) -> AssistedRepository.RegularityPlot:
        """Generate a regularity plot for the given activities.

        Args:
            *activities: Activity | str: The given activities.

        Returns:
            AssistedRepository.RegularityPlot: The regularity plot data.
        """

        sessions = self.find_by_activities(*activities)
        timeset = TimeSet.union(*(s.timeset for s in sessions))
        start = timeset.start.timestamp.floor_to_midnight()
        end = Timestamp.now().ceil_to_midnight()
        observations_range = TimeInterval.closed(start, end)

        half_window_duration = datetime.timedelta(weeks=1)
        # window_duration = 2 * half_window_duration

        # Calculate the regularity index for each midnight in the range
        # from `start` to `end`, using a centered two-week window.
        regularity_index: dict[Timestamp, float] = {}
        t = start
        while t <= end:
            window_start = t - half_window_duration
            window_end = t + half_window_duration
            window = (
                TimeInterval.closed(window_start, window_end)
                & observations_range
            )
            ri = self.regularity(*activities, timeinterval=window).index
            regularity_index[t] = ri
            t += datetime.timedelta(days=1)

        # Calculate the mean regularity index for each midnight
        # in the range from `start` to `end`, using a centered two-week
        # window.
        mean_regularity_index: dict [Timestamp, float] = {}
        t = start
        while t <= end:
            sum_start = max(start, t - half_window_duration)
            sum_end = min(end, t + half_window_duration)
            n = (sum_end - sum_start) / datetime.timedelta(days=1) + 1
            s = 0.
            tt = sum_start
            while tt <= sum_end:
                # Only take into account the values within the range.
                # Treat missing values as 0.
                s += regularity_index.get(tt, 0.)
                tt += datetime.timedelta(days=1)
            s /= n
            mean_regularity_index[t] = s
            t += datetime.timedelta(days=1)

        # Convert the mean regularity index to numpy arrays
        # for plotting.
        x_raw = np.array(
            [d.datetime.timestamp() for d in mean_regularity_index.keys()]
        )
        y_raw = np.array(list(mean_regularity_index.values()))

        # Smooth curve. If there are not enough points for cubic spline,
        # fall back to linear.
        if len(x_raw) < 4:
            x_smooth = x_raw
            y_smooth = y_raw
        else:
            x_smooth = np.linspace(
                x_raw.min(),
                x_raw.max(),
                300
            )
            spline = make_interp_spline(x_raw, y_raw, k=3)
            y_smooth = abs(spline(x_smooth))

        # Create tick positions and labels for the x-axis.
        raw_dates = list(mean_regularity_index.keys())
        raw_labels = [d.datetime.strftime('%Y-%m-%d') for d in raw_dates]
        # About 8 labels works nicely in terminals.
        n_ticks = min(8, len(raw_dates))
        tick_idx = np.linspace(0, len(raw_dates) - 1, n_ticks).astype(int)
        tick_positions = x_raw[tick_idx].tolist()
        tick_labels = [raw_labels[i] for i in tick_idx]

        return AssistedRepository.RegularityPlot(
            x=x_smooth.tolist(),
            y=y_smooth.tolist(),
            tick_positions=tick_positions,
            tick_labels=tick_labels
        )


    def habits(self) -> dict[frozenset[Activity], float]:
        """Determine current habits.

        Determines habits over the past week.

        Returns:
            dict[frozenset[Activity, float]]: Habits, in descending
            order of regularity.
        """

        # Pick out the activities from last week.
        half_window_duration = Duration.week()
        # window_duration = 2 * half_window_duration
        end_selection = Timestamp.now().ceil_to_midnight()
        start_selection = end_selection - half_window_duration
        last_interval = TimeInterval.closed(start_selection, end_selection)
        last_sessions = self.find_overlapping(last_interval)
        last_activities = set(s.activities for s in last_sessions)

        # Calculate the mean regularity index for each activity group
        # and filter out those below the habit threshold.
        mean_regularity_index = {}
        t = Timestamp.now().ceil_to_midnight()
        for aa in last_activities:
            ss = self.find_by_activities(*aa)

            timeset = TimeSet.union(*(s.timeset for s in ss)).span()
            start = timeset.start.timestamp.floor_to_midnight()
            end = Timestamp.now().ceil_to_midnight()
            observations_range = TimeInterval.closed(start, end)
            mri = self.mean_regularity_index(
                *aa,
                timestamp=t,
                observations_range=observations_range)
            if mri >= 0.3:
                mean_regularity_index[aa] = mri

        # Sort the habits by mean regularity index in descending order.
        mean_regularity_index = dict(sorted(
            mean_regularity_index.items(), key=itemgetter(1), reverse=True)
        )

        return mean_regularity_index