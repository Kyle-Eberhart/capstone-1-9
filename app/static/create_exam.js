(() => {
  function parseAllCourses() {
    const dataEl = document.getElementById("all-courses-data");
    if (dataEl) {
      const raw = dataEl.textContent || "";
      if (raw.trim().length > 0) {
        try {
          return JSON.parse(raw);
        } catch (err) {
          console.error("Failed to parse all courses data", err);
        }
      }
    }

    if (Array.isArray(window.all_courses)) {
      return window.all_courses;
    }

    return [];
  }

  function initCreateExamForm() {
    const form = document.getElementById("create-exam-form");
    if (!form || form.dataset.initialized === "true") {
      return;
    }

    const courseSelect = document.getElementById("course_number");
    const yearSelect = document.getElementById("quarter_year");
    const sectionsContainer = document.getElementById("sections-container");
    const durationFields = document.getElementById("duration-fields");
    const timedYes = document.getElementById("timed_yes");
    const timedNo = document.getElementById("timed_no");

    if (!courseSelect || !yearSelect || !sectionsContainer) {
      return;
    }

    const allCourses = parseAllCourses();
    if (!Array.isArray(allCourses) || allCourses.length === 0) {
      console.warn("No course data found for create exam form");
      return;
    }

    form.dataset.initialized = "true";

    function toggleDurationFields() {
      if (!durationFields || !timedYes) {
        return;
      }

      if (timedYes.checked) {
        durationFields.classList.add("active");
      } else {
        durationFields.classList.remove("active");
      }
    }

    window.toggleDurationFields = toggleDurationFields;

    function populateYears(selectedCourse) {
      const matching = allCourses.filter(c => c.course_number === selectedCourse);
      const years = [...new Set(matching.map(c => c.quarter_year))];

      yearSelect.innerHTML = '<option value="">Select Quarter/Year</option>';
      years.forEach(year => {
        const opt = document.createElement("option");
        opt.value = year;
        opt.textContent = year;
        yearSelect.appendChild(opt);
      });
    }

    function populateSections(selectedCourse, selectedYear) {
      const matching = allCourses
        .filter(c => c.course_number === selectedCourse && c.quarter_year === selectedYear)
        .map(c => c.section);
      const uniqueSections = [...new Set(matching)];

      sectionsContainer.innerHTML = "";
      uniqueSections.forEach(section => {
        const div = document.createElement("div");
        div.className = "section-checkbox";

        const input = document.createElement("input");
        input.type = "checkbox";
        input.name = "sections[]";
        input.value = section;
        input.id = `section-${section}`;

        const label = document.createElement("label");
        label.htmlFor = input.id;
        label.textContent = section;

        div.appendChild(input);
        div.appendChild(label);
        sectionsContainer.appendChild(div);
      });
    }

    function updateAll() {
      const selectedCourse = courseSelect.value;
      if (!selectedCourse) {
        yearSelect.innerHTML = '<option value="">Select Quarter/Year</option>';
        sectionsContainer.innerHTML = "";
        return;
      }

      populateYears(selectedCourse);
      const selectedYear = yearSelect.value;
      if (!selectedYear) {
        sectionsContainer.innerHTML = "";
        return;
      }

      populateSections(selectedCourse, selectedYear);
    }

    updateAll();

    toggleDurationFields();

    courseSelect.addEventListener("change", updateAll);
    yearSelect.addEventListener("change", () => {
      populateSections(courseSelect.value, yearSelect.value);
    });

    if (timedYes) {
      timedYes.addEventListener("change", toggleDurationFields);
    }
    if (timedNo) {
      timedNo.addEventListener("change", toggleDurationFields);
    }
  }

  window.initCreateExamForm = initCreateExamForm;
  document.addEventListener("DOMContentLoaded", initCreateExamForm);
  document.addEventListener("bluevox:content-loaded", initCreateExamForm);
})();
