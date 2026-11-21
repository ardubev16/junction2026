<!-- /about: what WikiCross does, what a finding's numbers mean (the "i" popover links to #numbers), its
     limits, and where the text comes from. Static text: keep it in step with docs/how-it-works.md. -->
<template>
  <article class="about">
    <h1>About WikiCross</h1>
    <p>
      WikiCross compares the Wikipedia editions of one topic, in every Latin- and Cyrillic-script language, and shows
      where they state the same thing differently: a different figure or date, a more favourable or critical tone, or a
      fact presented as settled in one edition and disputed in another.
    </p>

    <h2>How a finding is made</h2>
    <ol>
      <li>
        Every edition of the topic is fetched from Wikipedia, split into passages and sentences, and each is turned into
        a vector (bge-m3, one vector space for all languages).
      </li>
      <li>
        Passages and then sentences are paired across languages when each is the other's closest match. Sentences
        matched this way are grouped: one group per statement, one sentence per edition.
      </li>
      <li>
        A group becomes a candidate when one edition sits apart from the others on a tone axis (how positive, how
        certain, how loaded its wording is).
      </li>
      <li>
        A decision model reads every candidate's quotes and judges whether they really disagree, how, and how much.
        Candidates it finds no disagreement in are never shown.
      </li>
      <li>When a finding is shown, an AI writes its title and summary and translates its quotes into English.</li>
    </ol>

    <h2 id="numbers">The numbers behind a finding</h2>
    <dl>
      <dt>Decision model</dt>
      <dd>
        The kind of disagreement: <b>factual</b> (statements that cannot all be true), <b>bias</b> (one edition clearly
        more favourable or critical, or loaded wording), or <b>framing</b> (the same facts, presented as more or less
        certain). Then how likely the quotes are to disagree at all, and how much a reader would care: minor, notable or
        major, on a scale from 0 to 2. Findings are listed by likelihood times strength.
      </dd>
      <dt>Stands apart</dt>
      <dd>With three editions or more, the one whose quote differs from the others, if one does.</dd>
      <dt>Match</dt>
      <dd>
        The largest cosine distance between two sentences of the group: 0 is the same meaning. Up to 0.35, sentences
        count as one statement.
      </dd>
      <dt>Tone</dt>
      <dd>
        How far the edition furthest along a tone axis sits from the others, in standard deviations (σ) of its own
        language's sentences. A candidate needs 1.2σ. This is why the group was looked at, not a verdict.
      </dd>
    </dl>

    <h2>Limits</h2>
    <ul>
      <li>
        The models can be wrong. Each quote links to its place on Wikipedia: check it there before relying on a finding.
      </li>
      <li>
        What most editions say is not necessarily true: editions often copy one another, or give a value for different
        dates.
      </li>
      <li>Facts that only one edition states are never shown: WikiCross is about disagreement, not omission.</li>
      <li>Only Latin- and Cyrillic-script editions are compared for now.</li>
    </ul>

    <h2>Sources</h2>
    <p>
      Quotes are from Wikipedia, by its contributors, under the
      <a href="https://creativecommons.org/licenses/by-sa/4.0/" rel="license"
        >Creative Commons Attribution-ShareAlike 4.0</a
      >
      license; each one links to its article. Translations are machine-made. WikiCross is an independent project, not
      affiliated with or endorsed by the Wikimedia Foundation. Its
      <a href="https://github.com/ardubev16/junction2026">source code</a> is free software (GPL-3.0-or-later).
    </p>
  </article>
</template>
