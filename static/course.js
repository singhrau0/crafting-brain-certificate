const course = document.querySelector("#course");
const custom = document.querySelector("#custom");
function updateCourse() {
  custom.hidden = course.value !== "Other";
  custom.querySelector("input").required = !custom.hidden;
}
course.addEventListener("change", updateCourse);
updateCourse();
