const body = document.body;
const menuToggle = document.querySelector(".menu-toggle");
const slides = Array.from(document.querySelectorAll(".hero-slide"));
const progress = Array.from(document.querySelectorAll(".hero-progress span"));
const revealItems = Array.from(document.querySelectorAll(".reveal"));
const counters = Array.from(document.querySelectorAll("[data-count]"));
const newsletter = document.querySelector(".newsletter");

menuToggle?.addEventListener("click", () => {
  const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
  menuToggle.setAttribute("aria-expanded", String(!isOpen));
  body.classList.toggle("menu-open", !isOpen);
});

document.querySelectorAll(".site-nav a").forEach((link) => {
  link.addEventListener("click", () => {
    body.classList.remove("menu-open");
    menuToggle?.setAttribute("aria-expanded", "false");
  });
});

let activeSlide = 0;

function showSlide(index) {
  slides.forEach((slide, slideIndex) => {
    slide.classList.toggle("is-active", slideIndex === index);
  });

  progress.forEach((item, itemIndex) => {
    item.classList.toggle("is-active", itemIndex === index);
  });
}

if (slides.length > 1 && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  window.setInterval(() => {
    activeSlide = (activeSlide + 1) % slides.length;
    showSlide(activeSlide);
  }, 5200);
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-SG").format(value);
}

function animateCounter(element) {
  const target = Number(element.dataset.count);
  const duration = 1400;
  const start = performance.now();

  function step(now) {
    const progressValue = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progressValue, 3);
    element.textContent = formatNumber(Math.round(target * eased));

    if (progressValue < 1) {
      requestAnimationFrame(step);
    }
  }

  requestAnimationFrame(step);
}

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;

      entry.target.classList.add("is-visible");

      if (entry.target.matches("[data-count]") && !entry.target.dataset.counted) {
        entry.target.dataset.counted = "true";
        animateCounter(entry.target);
      }

      observer.unobserve(entry.target);
    });
  },
  { threshold: 0.2 }
);

revealItems.forEach((item) => observer.observe(item));
counters.forEach((counter) => observer.observe(counter));

newsletter?.addEventListener("submit", (event) => {
  event.preventDefault();

  const form = event.currentTarget;
  const email = form.email.value.trim();
  const note = form.querySelector(".form-note");

  note.classList.remove("is-success", "is-warning");

  if (!email || !email.includes("@")) {
    note.textContent = "Enter a valid email to continue.";
    note.classList.add("is-warning");
    form.email.focus();
    return;
  }

  note.textContent = "Thanks. This static demo is ready to connect to EG's newsletter service.";
  note.classList.add("is-success");
  form.reset();
});
