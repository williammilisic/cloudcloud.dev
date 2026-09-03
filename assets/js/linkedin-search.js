/*
 * Keyword search over the LinkedIn archive.
 *
 * The site is static, so there is nowhere to run a query but the browser. The
 * whole index is fetched once and matched here, which is affordable at this size
 * and means no search term ever leaves the machine it was typed on.
 *
 * Post text is scraped, so it is only ever placed on the page as text nodes.
 * Nothing here builds markup out of it.
 */
(function () {
  'use strict';

  var results = document.getElementById('search-results');
  var status = document.getElementById('search-status');
  var input = document.getElementById('search-query');
  var moreButton = document.getElementById('search-more');
  var form = document.querySelector('.archive-search');
  if (!results || !status || !input) {
    return;
  }

  var PAGE_SIZE = 25;
  var SNIPPET_BEFORE = 90;
  var SNIPPET_AFTER = 230;
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  var posts = [];
  var matches = [];
  var shown = 0;
  var terms = [];

  /* Case and accents are folded so that a search for "arbetssatt" still finds
     "arbetssätt". Each character maps to exactly one character so that positions
     in the folded text are also positions in the original, which is what lets
     the snippet highlight the right span. */
  var foldCache = {};

  function foldCharacter(character) {
    var cached = foldCache[character];
    if (cached !== undefined) {
      return cached;
    }
    var lowered = character.toLowerCase();
    var base = lowered;
    if (String.prototype.normalize) {
      base = lowered.normalize('NFD').charAt(0);
    } else {
      base = lowered.charAt(0);
    }
    if (base === '') {
      base = character;
    }
    foldCache[character] = base;
    return base;
  }

  function fold(text) {
    var out = '';
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code >= 65 && code <= 90) {
        out += String.fromCharCode(code + 32);
      } else if (code < 128) {
        out += text.charAt(i);
      } else {
        out += foldCharacter(text.charAt(i));
      }
    }
    return out;
  }

  /* Quoted runs stay together, everything else is a word that has to appear. */
  function parseQuery(raw) {
    var pattern = /"([^"]*)"|(\S+)/g;
    var found = [];
    var match;
    while ((match = pattern.exec(raw)) !== null) {
      var piece = match[1] !== undefined ? match[1] : match[2];
      var folded = fold(piece).trim();
      if (folded) {
        found.push(folded);
      }
    }
    return found;
  }

  function formatDate(day) {
    var parts = String(day).split('-');
    if (parts.length !== 3) {
      return String(day);
    }
    var month = MONTHS[parseInt(parts[1], 10) - 1] || parts[1];
    return month + ' ' + parseInt(parts[2], 10) + ', ' + parts[0];
  }

  function countLabel(count, singular, plural) {
    return count.toLocaleString() + ' ' + (count === 1 ? singular : plural);
  }

  /* Where to cut the snippet: around the first term that actually appears, so
     the excerpt shows the match rather than always the opening line. */
  function firstHit(foldedText) {
    var earliest = -1;
    for (var i = 0; i < terms.length; i++) {
      var at = foldedText.indexOf(terms[i]);
      if (at !== -1 && (earliest === -1 || at < earliest)) {
        earliest = at;
      }
    }
    return earliest;
  }

  function buildSnippet(post) {
    var text = post.t;
    var at = firstHit(post.folded);
    if (at === -1) {
      at = 0;
    }
    var start = Math.max(0, at - SNIPPET_BEFORE);
    var end = Math.min(text.length, at + SNIPPET_AFTER);

    /* Avoid slicing through a word at either edge. */
    if (start > 0) {
      var space = text.indexOf(' ', start);
      if (space !== -1 && space < at) {
        start = space + 1;
      }
    }
    if (end < text.length) {
      var lastSpace = text.lastIndexOf(' ', end);
      if (lastSpace > at) {
        end = lastSpace;
      }
    }

    return {
      text: (start > 0 ? '\u2026' : '') + text.slice(start, end) + (end < text.length ? '\u2026' : ''),
      offset: start - (start > 0 ? 1 : 0)
    };
  }

  /* Marks every occurrence of every term, built as text nodes and <mark>
     elements rather than as a string of markup. */
  function highlighted(snippet) {
    var folded = fold(snippet);
    var spans = [];
    for (var i = 0; i < terms.length; i++) {
      var term = terms[i];
      var from = 0;
      var at;
      while ((at = folded.indexOf(term, from)) !== -1) {
        spans.push([at, at + term.length]);
        from = at + term.length;
      }
    }
    spans.sort(function (a, b) { return a[0] - b[0]; });

    var merged = [];
    for (var j = 0; j < spans.length; j++) {
      var last = merged[merged.length - 1];
      if (last && spans[j][0] <= last[1]) {
        last[1] = Math.max(last[1], spans[j][1]);
      } else {
        merged.push([spans[j][0], spans[j][1]]);
      }
    }

    var fragment = document.createDocumentFragment();
    var cursor = 0;
    for (var k = 0; k < merged.length; k++) {
      if (merged[k][0] > cursor) {
        fragment.appendChild(document.createTextNode(snippet.slice(cursor, merged[k][0])));
      }
      var mark = document.createElement('mark');
      mark.textContent = snippet.slice(merged[k][0], merged[k][1]);
      fragment.appendChild(mark);
      cursor = merged[k][1];
    }
    if (cursor < snippet.length) {
      fragment.appendChild(document.createTextNode(snippet.slice(cursor)));
    }
    return fragment;
  }

  /* The same shape as the cards elsewhere in the archive, so one stylesheet
     covers both. */
  function card(post) {
    var wrapper = document.createElement('div');
    wrapper.className = 'linkedin-post-card' + (post.a ? ' linkedin-post-repost' : '');

    var inner = document.createElement('div');
    inner.className = 'linkedin-post-text';
    wrapper.appendChild(inner);

    if (post.a) {
      var author = document.createElement('p');
      author.className = 'linkedin-post-author';
      var icon = document.createElement('i');
      icon.className = 'fas fa-retweet';
      icon.setAttribute('aria-hidden', 'true');
      author.appendChild(icon);
      author.appendChild(document.createTextNode(' Reposted from ' + post.a));
      inner.appendChild(author);
    }

    var body = document.createElement('div');
    body.className = 'linkedin-post-body';
    var snippet = buildSnippet(post);
    body.appendChild(highlighted(snippet.text));
    inner.appendChild(body);

    var meta = document.createElement('p');
    meta.className = 'linkedin-post-description';
    meta.appendChild(document.createTextNode('Posted on ' + formatDate(post.d) + ' \u00b7 '));

    var year = parseInt(String(post.d).slice(0, 4), 10);
    var label = year < 2018 ? 'Read on LinkedIn (sign-in required)' : 'Read on LinkedIn';
    if (post.u) {
      var link = document.createElement('a');
      link.className = 'linkedin-post-link';
      link.href = post.u;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = label;
      meta.appendChild(link);
    } else {
      meta.appendChild(document.createTextNode(label));
    }
    if (post.x) {
      meta.appendChild(document.createTextNode(' \u00b7 preview only, full text unavailable'));
    }
    inner.appendChild(meta);

    return wrapper;
  }

  function renderMore() {
    var fragment = document.createDocumentFragment();
    var until = Math.min(matches.length, shown + PAGE_SIZE);
    for (var i = shown; i < until; i++) {
      fragment.appendChild(card(matches[i]));
    }
    results.appendChild(fragment);
    shown = until;
    if (moreButton) {
      moreButton.hidden = shown >= matches.length;
      if (!moreButton.hidden) {
        moreButton.textContent = 'Show more (' + (matches.length - shown) + ' left)';
      }
    }
  }

  function search(raw) {
    terms = parseQuery(raw);
    results.textContent = '';
    shown = 0;
    matches = [];
    if (moreButton) {
      moreButton.hidden = true;
    }

    if (!terms.length) {
      status.textContent = 'Ready to search ' + countLabel(posts.length, 'post', 'posts') + '.';
      return;
    }

    for (var i = 0; i < posts.length; i++) {
      var haystack = posts[i].haystack;
      var all = true;
      for (var j = 0; j < terms.length; j++) {
        if (haystack.indexOf(terms[j]) === -1) {
          all = false;
          break;
        }
      }
      if (all) {
        matches.push(posts[i]);
      }
    }

    if (!matches.length) {
      status.textContent = 'No posts match that.';
      return;
    }
    status.textContent = countLabel(matches.length, 'post matches', 'posts match') +
      ', newest first.';
    renderMore();
  }

  function rememberQuery(raw) {
    if (!window.history || !window.history.replaceState) {
      return;
    }
    var base = window.location.pathname;
    var url = raw ? base + '?q=' + encodeURIComponent(raw) : base;
    window.history.replaceState(null, '', url);
  }

  function queryFromUrl() {
    var match = /[?&]q=([^&]*)/.exec(window.location.search);
    if (!match) {
      return '';
    }
    try {
      return decodeURIComponent(match[1].replace(/\+/g, ' '));
    } catch (error) {
      return '';
    }
  }

  var pending = null;
  function scheduleSearch() {
    if (pending) {
      window.clearTimeout(pending);
    }
    pending = window.setTimeout(function () {
      pending = null;
      var raw = input.value;
      search(raw);
      rememberQuery(raw);
    }, 150);
  }

  if (form) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      if (pending) {
        window.clearTimeout(pending);
        pending = null;
      }
      search(input.value);
      rememberQuery(input.value);
    });
  }
  input.addEventListener('input', scheduleSearch);
  if (moreButton) {
    moreButton.addEventListener('click', renderMore);
  }

  var indexUrl = results.getAttribute('data-index');
  fetch(indexUrl, { credentials: 'omit' })
    .then(function (response) {
      if (!response.ok) {
        throw new Error('the archive returned ' + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      posts = data;
      /* Folded once here rather than on every keystroke. The author is part of
         what is matched so that a name finds the posts reposted from them. */
      for (var i = 0; i < posts.length; i++) {
        posts[i].folded = fold(posts[i].t || '');
        posts[i].haystack = posts[i].a ? posts[i].folded + ' ' + fold(posts[i].a) : posts[i].folded;
      }
      input.disabled = false;
      var initial = queryFromUrl();
      if (initial) {
        input.value = initial;
        search(initial);
      } else {
        status.textContent = 'Ready to search ' + countLabel(posts.length, 'post', 'posts') + '.';
      }
      input.focus();
    })
    .catch(function (error) {
      status.textContent = 'The archive could not be loaded (' + error.message +
        '). The year links above still work.';
    });
}());
