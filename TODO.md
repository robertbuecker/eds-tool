**Fitting**
* Provide library of standard backgrounds for different holders/grids
* How can we speed up typical workflows for fitting
* Proper handling of fitting of many spectra at once for more complex workflows involving optimizing fits on a single spectrum and propagating
* Enable fine-tuning of peak positions (individually or overall scale/position)
* Here's what to look into: https://exspy.readthedocs.io/en/latest/reference/models.html

**BG handling**
* Work out consistent ways of subtracting background in displayed/exported spectra, depending on how BG is treated. 
* UX should somehow allow, but discourage direct subtraction of background spectrum from the raw data. BG handling by fitting is clearly preferred and needs to be obvious and straightforward

**General workflows**
* Routine for automatic full qualitative analysis with iterative adding of elements. BG handling needs to be carefully considered - full fitting would be preferred, but is likely too slow (or can it be made faster?), so some workaround just using peak identification (with seeding with known BG elements)