function updateStepParamsUI(stepDiv, step) {
  const container = stepDiv.querySelector('.step-params-container');
  const action = stepDiv.querySelector('.step-action').value;
  container.innerHTML = ''; // Clear existing params
  container.style.display = 'flex'; // Align items horizontally

  const createSelect = (name, options, selectedValue) => {
    const select = document.createElement('select');
    select.className = 'form-select me-2';
    select.name = name;
    select.style.flex = '1'; // Equal width inside the container
    options.forEach(optionValue => {
      const option = document.createElement('option');
      option.value = optionValue;
      option.textContent = optionValue;
      if (selectedValue === optionValue) {
        option.selected = true;
      }
      select.appendChild(option);
    });
    select.addEventListener('change', updateTaskJsonPreview);
    return select;
  };

  if (action === 'move_shelf') {
    const shelfSelect = createSelect('shelf_id', SHELVES, step.params?.shelf_id);
    const locationSelect = createSelect('location_id', LOCATIONS, step.params?.location_id);
    container.appendChild(shelfSelect);
    container.appendChild(locationSelect);
  } else if (action === 'move_to_location') {
    const locationSelect = createSelect('location_id', LOCATIONS, step.params?.location_id);
    container.appendChild(locationSelect);
  }
  updateTaskJsonPreview();
}
