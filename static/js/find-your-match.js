(function () {
  "use strict";

  function parseConfig(root) {
    var node = root.querySelector("#find-match-config");
    if (!node) {
      throw new Error("Missing Find Your Match config.");
    }
    return JSON.parse(node.textContent);
  }

  function formatTemplate(template, values) {
    return String(template || "")
      .replace(/\{answered\}/g, String(values.answered))
      .replace(/\{total\}/g, String(values.total));
  }

  function normalizeCriterion(score, direction, positive) {
    var numeric = Number(score);
    if (!Number.isFinite(numeric)) {
      numeric = 3;
    }

    var highValue = numeric;
    var lowValue = 6 - numeric;

    if (direction === "lower") {
      highValue = 6 - numeric;
      lowValue = numeric;
    }

    return positive ? highValue : lowValue;
  }

  function scoreStyle(style, selectedAnswers, config) {
    var total = 0;
    var scoring = config.answerScoring || {};
    var directions = config.criteriaDirections || {};

    selectedAnswers.forEach(function (answer) {
      var questionScoring = scoring[answer.questionId] || {};
      var answerScoring = questionScoring[answer.value] || {};
      var criteria = answerScoring.criteria || {};

      Object.keys(criteria).forEach(function (criterion) {
        var weight = Number(criteria[criterion]);
        if (!Number.isFinite(weight) || weight === 0) {
          return;
        }

        var positive = weight > 0;
        var direction = directions[criterion] || "higher";
        var score = style.baseline_scores && style.baseline_scores[criterion];
        total += normalizeCriterion(score, direction, positive) * Math.abs(weight);
      });

      var axes = answerScoring.axes || {};
      Object.keys(axes).forEach(function (axisName) {
        var axisWeights = axes[axisName] || {};
        var styleValue = style.structural_axes && style.structural_axes[axisName];

        if (!styleValue) {
          return;
        }

        Object.keys(axisWeights).forEach(function (expectedValue) {
          var axisWeight = Number(axisWeights[expectedValue]);
          if (!Number.isFinite(axisWeight)) {
            return;
          }

          if (String(styleValue).toLowerCase() === String(expectedValue).toLowerCase()) {
            total += axisWeight * 5;
          }
        });
      });
    });

    return total;
  }

  function collectSelectedAnswers(form) {
    var checked = form.querySelectorAll("input[type='radio']:checked");
    return Array.prototype.map.call(checked, function (input) {
      return {
        questionId: input.getAttribute("data-question-id"),
        value: input.value
      };
    });
  }

  function clearResults(root) {
    var results = root.querySelector("[data-match-results]");
    var grid = root.querySelector("[data-match-results-grid]");
    if (grid) {
      grid.innerHTML = "";
    }
    if (results) {
      results.hidden = true;
    }
  }

  function renderResults(root, config, ranked) {
    var results = root.querySelector("[data-match-results]");
    var grid = root.querySelector("[data-match-results-grid]");

    if (!results || !grid) {
      return;
    }

    grid.innerHTML = "";

    ranked.slice(0, 3).forEach(function (row, index) {
      var article = document.createElement("article");
      article.className = "find-match-result-card";
      article.setAttribute("data-rank", String(index + 1));

      var badge = document.createElement("span");
      badge.className = "find-match-result-card__rank";
      badge.textContent = index === 0 ? "01" : "0" + String(index + 1);

      var title = document.createElement("h3");
      title.textContent = row.style.title;

      var summary = document.createElement("p");
      summary.textContent = row.style.summary;

      var score = document.createElement("strong");
      score.className = "find-match-result-card__score";
      score.textContent = Math.round(row.score) + " " + ((config.copy && config.copy.scoreLabel) || "Match score");

      var link = document.createElement("a");
      link.className = "find-match-result-card__link";
      link.href = row.style.href;
      link.textContent = (config.copy && config.copy.openLabel) || "Open reference page";

      article.appendChild(badge);
      article.appendChild(title);
      article.appendChild(summary);
      article.appendChild(score);
      article.appendChild(link);
      grid.appendChild(article);
    });

    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function updateProgress(root, form, config) {
    var selected = collectSelectedAnswers(form);
    var total = Number(config.questionCount || 6);
    var answered = selected.length;
    var percent = Math.min(100, Math.round((answered / total) * 100));

    var bar = root.querySelector("[data-match-progress-bar]");
    var text = root.querySelector("[data-match-progress-text]");

    if (bar) {
      bar.style.width = percent + "%";
    }

    if (text) {
      var template =
        config.copy && config.copy.progressTemplate
          ? config.copy.progressTemplate
          : "{answered} of {total} questions answered";

      text.textContent = formatTemplate(template, {
        answered: answered,
        total: total
      });
    }
  }

  function initialize(root) {
    var config = parseConfig(root);
    var form = root.querySelector("[data-match-form]");
    var reset = root.querySelector("[data-match-reset]");
    var notice = root.querySelector("[data-match-notice]");

    if (!form) {
      return;
    }

    form.addEventListener("change", function () {
      updateProgress(root, form, config);
      if (notice) {
        notice.hidden = true;
      }
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      var selected = collectSelectedAnswers(form);
      var requiredCount = Number(config.questionCount || 6);

      if (selected.length < requiredCount) {
        if (notice) {
          notice.hidden = false;
        }
        clearResults(root);
        return;
      }

      var styles = Array.isArray(config.styles) ? config.styles : [];
      var ranked = styles
        .map(function (style) {
          return {
            style: style,
            score: scoreStyle(style, selected, config)
          };
        })
        .sort(function (a, b) {
          return b.score - a.score;
        });

      renderResults(root, config, ranked);
    });

    if (reset) {
      reset.addEventListener("click", function () {
        form.reset();
        clearResults(root);
        if (notice) {
          notice.hidden = true;
        }
        updateProgress(root, form, config);
      });
    }

    updateProgress(root, form, config);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var roots = document.querySelectorAll("[data-match-tool]");
    Array.prototype.forEach.call(roots, function (root) {
      try {
        initialize(root);
      } catch (error) {
        console.error("Find Your Match failed to initialize:", error);
      }
    });
  });
})();
