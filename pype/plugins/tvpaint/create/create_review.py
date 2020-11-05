from avalon.tvpaint import pipeline


class CreateReview(pipeline.TVPaintCreator):
    """Review for global review of all layers."""
    name = "review"
    label = "Review"
    family = "review"
    icon = "cube"
    defaults = ["Main"]

    def process(self):
        instances = pipeline.list_instances()
        for instance in instances:
            if instance["family"] == self.family:
                self.log.info("Review family is already Created.")
                return
        super(CreateReview, self).process()
