from tests.fixtures.sample_pkg.utils import double


class Service:
    def run(self, x):
        return self.validate(double(x))

    def validate(self, x):
        if x < 0:
            raise ValueError("negative")
        return x
