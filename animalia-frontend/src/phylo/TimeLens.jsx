import { formatAge } from '../phylogenyLayout.js'
import { periodAt } from '../phylogenyStyle.js'

// The narration bar for travelling through deep time. The lens itself (the
// cursor on the tree) is drawn by TreeCanvas; this holds play, the scrubber
// and what is happening at the current moment.
export default function TimeLens({ rootAge, lensAge, playing, events, onPlay, onScrub, onExit }) {
  const active = lensAge != null
  const age = active ? lensAge : 0
  const period = periodAt(age)
  const event = active ? [...events].reverse().find((e) => e.age >= age) ?? events[0] : null
  const atPresent = active && age <= 0

  return (
    <div className={`time-lens${active ? ' active' : ''}${atPresent ? ' present' : ''}`}>
      <button
        type="button"
        className="lens-play"
        onClick={onPlay}
        aria-label={playing ? 'Pause' : 'Play evolutionary history'}
      >
        {playing ? '❚❚' : '▶'}
      </button>
      <div className="lens-track">
        <label className="sr-only" htmlFor="lens-range">Time (millions of years ago)</label>
        <input
          id="lens-range"
          type="range"
          min={0}
          max={rootAge}
          step={0.5}
          value={rootAge - age}
          onChange={(event) => {
            const next = rootAge - Number(event.target.value)
            onScrub(next < 0.5 ? 0 : next) // the last half-step is the present
          }}
          aria-valuetext={`${formatAge(age)} million years ago`}
        />
        <div className="lens-ends" aria-hidden="true">
          <span>{Math.round(rootAge)} Ma</span>
          <span>Today</span>
        </div>
      </div>
      <div className="lens-narration" aria-live="polite">
        {active ? (
          <>
            <p className="lens-period" key={period.name}>
              {atPresent ? 'The present' : period.name}
              <span>{atPresent ? '' : ` · ${formatAge(age)} million years ago`}</span>
            </p>
            {event && (
              <p className="lens-event" key={`${event.title}-${event.age}`}>
                {!atPresent && <strong>{event.title} — </strong>}
                {event.text}
                {event.age > 0 ? ` (~${formatAge(event.age)} Ma)` : ''}
              </p>
            )}
          </>
        ) : (
          <p className="lens-hint">Travel through deep time: press play or drag the slider.</p>
        )}
      </div>
      {active && (
        <button type="button" className="lens-exit" onClick={onExit}>
          Show full tree
        </button>
      )}
    </div>
  )
}
