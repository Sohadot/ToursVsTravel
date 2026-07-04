/*
 * TourVsTravel — Travel Decision Compass
 * Client-side implementation of the Structure Fit Protocol (SFP):
 *   1. classify  — candidates are the 17 TSO structures (embedded payload)
 *   2. score-fit — proximity across the six structural axes + traveler profile
 *   3. apply-standard — priors contextualized, uncertainty declared, no winner
 *   4. emit-diagnosis — ranked fit, explicit tradeoffs, links to class pages
 *
 * No network calls, no storage, no tracking. All data ships in the page.
 */
(function () {
  "use strict";

  var SCALES = {
    structure_intensity: ["low", "medium", "high"],
    autonomy_level: ["low", "medium", "high"],
    support_level: ["low", "medium", "high"],
    pace_profile: ["fixed", "balanced", "flexible"],
    immersion_profile: ["surface", "balanced", "deep"],
    predictability_profile: ["low", "medium", "high"],
  };
  var AXIS_IDS = Object.keys(SCALES);
  var AFFINITY_POINTS = { high: 2, medium: 1, low: 0 };
  var AXIS_MATCH_MAX = 2;
  var PROFILE_WEIGHT = 2;

  function axisProximity(axisId, wanted, actual) {
    var scale = SCALES[axisId];
    var a = scale.indexOf(wanted);
    var b = scale.indexOf(actual);
    if (a < 0 || b < 0) {
      return 0;
    }
    var distance = Math.abs(a - b);
    return Math.max(0, AXIS_MATCH_MAX - distance);
  }

  function scoreStructure(structure, answers) {
    var axisPoints = 0;
    var perAxis = {};
    AXIS_IDS.forEach(function (axisId) {
      var wanted = answers[axisId];
      var actual = structure.structural_axes[axisId];
      var points = axisProximity(axisId, wanted, actual);
      perAxis[axisId] = points;
      axisPoints += points;
    });

    var affinity = structure.profile_affinity[answers.traveler_profile] || "low";
    var profilePoints = (AFFINITY_POINTS[affinity] || 0) * PROFILE_WEIGHT;

    var maxPoints = AXIS_IDS.length * AXIS_MATCH_MAX + AFFINITY_POINTS.high * PROFILE_WEIGHT;
    var score = Math.round(((axisPoints + profilePoints) / maxPoints) * 100);

    return { structure: structure, score: score, perAxis: perAxis, affinity: affinity };
  }

  function bandFor(score, bands) {
    for (var i = 0; i < bands.length; i += 1) {
      if (score >= bands[i].min && score <= bands[i].max) {
        return bands[i];
      }
    }
    return bands[bands.length - 1];
  }

  function alignmentSummary(result, config) {
    var matched = [];
    var traded = [];
    AXIS_IDS.forEach(function (axisId) {
      var entry = {
        axis: config.axis_names[axisId] || axisId,
        value: config.value_labels[result.structure.structural_axes[axisId]] ||
          result.structure.structural_axes[axisId],
      };
      if (result.perAxis[axisId] === AXIS_MATCH_MAX) {
        matched.push(entry);
      } else if (result.perAxis[axisId] === 0) {
        traded.push(entry);
      }
    });
    return { matched: matched, traded: traded };
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text) {
      node.textContent = text;
    }
    return node;
  }

  function renderAxisList(container, labelText, items) {
    if (!items.length) {
      return;
    }
    var wrap = el("p", "compass-result__axes");
    wrap.appendChild(el("strong", null, labelText + " "));
    wrap.appendChild(
      document.createTextNode(
        items
          .map(function (item) {
            return item.axis + " (" + item.value + ")";
          })
          .join(" · ")
      )
    );
    container.appendChild(wrap);
  }

  function renderResults(results, config, mount) {
    mount.textContent = "";

    var heading = el("h2", "compass-results__title", config.copy.results_title);
    mount.appendChild(heading);

    results.forEach(function (result, index) {
      var band = bandFor(result.score, config.score_bands);
      var card = el("article", "compass-result travel-architecture-section");

      var title = el("h3", "compass-result__title");
      var link = el("a", null, result.structure.label);
      link.setAttribute("href", result.structure.url);
      title.appendChild(document.createTextNode(String(index + 1) + ". "));
      title.appendChild(link);
      card.appendChild(title);

      card.appendChild(
        el(
          "p",
          "compass-result__band",
          band.label + " — " + result.score + "/100"
        )
      );
      card.appendChild(el("p", "compass-result__summary", result.structure.summary));

      var alignment = alignmentSummary(result, config);
      renderAxisList(card, config.copy.matched_label, alignment.matched);
      renderAxisList(card, config.copy.traded_label, alignment.traded);

      card.appendChild(
        el("p", "compass-result__citation", config.copy.citation_label + ": " + result.structure.citation)
      );
      mount.appendChild(card);
    });

    var note = el("p", "compass-results__note", config.copy.priors_note);
    mount.appendChild(note);

    mount.removeAttribute("hidden");
    if (typeof mount.focus === "function") {
      mount.setAttribute("tabindex", "-1");
      mount.focus({ preventScroll: false });
    }
  }

  function collectAnswers(form) {
    var answers = {};
    var complete = true;
    var fields = AXIS_IDS.concat(["traveler_profile"]);
    fields.forEach(function (fieldId) {
      var checked = form.querySelector('input[name="' + fieldId + '"]:checked');
      if (checked) {
        answers[fieldId] = checked.value;
      } else {
        complete = false;
      }
    });
    return { answers: answers, complete: complete };
  }

  function init() {
    var root = document.querySelector("[data-compass-tool]");
    if (!root) {
      return;
    }
    var configNode = document.getElementById("compass-config");
    if (!configNode) {
      return;
    }

    var config;
    try {
      config = JSON.parse(configNode.textContent);
    } catch (error) {
      return;
    }

    var form = root.querySelector("[data-compass-form]");
    var mount = root.querySelector("[data-compass-results]");
    var errorNode = root.querySelector("[data-compass-error]");
    if (!form || !mount) {
      return;
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var collected = collectAnswers(form);

      if (!collected.complete) {
        if (errorNode) {
          errorNode.textContent = config.copy.incomplete_error;
          errorNode.removeAttribute("hidden");
        }
        return;
      }
      if (errorNode) {
        errorNode.setAttribute("hidden", "hidden");
      }

      var results = config.structures
        .map(function (structure) {
          return scoreStructure(structure, collected.answers);
        })
        .sort(function (a, b) {
          return b.score - a.score || a.structure.order - b.structure.order;
        })
        .slice(0, config.max_results);

      renderResults(results, config, mount);
    });

    form.addEventListener("reset", function () {
      mount.setAttribute("hidden", "hidden");
      mount.textContent = "";
      if (errorNode) {
        errorNode.setAttribute("hidden", "hidden");
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
